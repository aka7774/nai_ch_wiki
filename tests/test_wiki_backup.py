import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scrapy.http import HtmlResponse

from seesawiki_back_up.crawl import main
from seesawiki_back_up.spiders.backup import BackupSpider


ROOT_DIR = Path(__file__).resolve().parents[1]


def response(html):
    return HtmlResponse(
        "https://seesaawiki.jp/nai_ch/l/?p=0",
        body=html.encode("utf-8"),
        encoding="utf-8",
    )


class WikiSpiderTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_yields_one_listing_request(self):
        spider = BackupSpider()
        requests = [request async for request in spider.start()]
        self.assertEqual(1, len(requests))
        self.assertEqual(
            "https://seesaawiki.jp/nai_ch/l/?p=0&order=lastupdate&on_desc=1",
            requests[0].url,
        )
        self.assertEqual(spider.parse, requests[0].callback)

    def test_last_listing_still_yields_article(self):
        requests = list(BackupSpider().parse(response(
            '<ul class="page-list"><li><a href="/nai_ch/d/page">Page</a></li></ul>'
        )))
        self.assertEqual(1, len(requests))
        self.assertEqual("https://seesaawiki.jp/nai_ch/d/page", requests[0].url)
        self.assertEqual({"title": "Page"}, requests[0].cb_kwargs)

    def test_next_listing_resolves_relative_url(self):
        requests = list(BackupSpider().parse(response(
            '<li class="next"><a href="?p=1">Next</a></li>'
        )))
        self.assertEqual("https://seesaawiki.jp/nai_ch/l/?p=1", requests[0].url)

    def test_locked_article_has_no_edit_request(self):
        self.assertEqual([], list(BackupSpider().parse_article_page(response(""), "Page")))

    def test_missing_editor_does_not_yield_item(self):
        self.assertEqual([], list(BackupSpider().parse_edit_page(response(""), "Page")))

    def test_editor_text_is_extracted(self):
        items = list(BackupSpider().parse_edit_page(
            response('<textarea id="content">wiki &amp; markup</textarea>'), "Page"
        ))
        self.assertEqual("wiki & markup", items[0]["text"])


class WikiCommandTests(unittest.TestCase):
    def run_mock_crawl(self, saved_pages, bootstrap_failed=False):
        with TemporaryDirectory() as tmpdir, patch(
            "seesawiki_back_up.crawl.CrawlerProcess"
        ) as process_class:
            process = process_class.return_value
            process.bootstrap_failed = bootstrap_failed
            crawler = process.create_crawler.return_value
            crawler.stats.get_value.return_value = saved_pages
            return main(["backup", "--save-dir", tmpdir])

    def test_zero_saved_pages_fails(self):
        self.assertEqual(1, self.run_mock_crawl(0))

    def test_saved_page_succeeds(self):
        self.assertEqual(0, self.run_mock_crawl(1))

    def test_startup_failure_fails(self):
        self.assertEqual(1, self.run_mock_crawl(1, bootstrap_failed=True))

    def run_offline_command(self, start_body, save_dir):
        # A fresh subprocess runs the real reactor, pipeline and script exit path.
        # The empty/data-only start method never makes a network request.
        script = f'''
import runpy
import sys
import scrapy
from seesawiki_back_up.spiders.backup import BackupSpider
async def start(self):
{start_body}
BackupSpider.start = start
sys.argv = ["crawl.py", "backup", "--save-dir", sys.argv[1],
            "-s", "LOG_LEVEL=ERROR", "-s", "TELNETCONSOLE_ENABLED=False"]
runpy.run_path("seesawiki_back_up/crawl.py", run_name="__main__")
'''
        return subprocess.run(
            [sys.executable, "-c", script, str(save_dir)],
            cwd=ROOT_DIR, capture_output=True, text=True, timeout=30,
        )

    def test_real_empty_crawl_exits_nonzero_even_with_old_file(self):
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            (output / "old.txt").write_text("old backup", encoding="utf-8")
            result = self.run_offline_command("    if False:\n        yield", output)
            self.assertEqual(1, result.returncode, result.stderr)
            self.assertIn("no pages saved", result.stderr)
            self.assertEqual("old backup", (output / "old.txt").read_text(encoding="utf-8"))

    def test_real_saved_page_exits_zero(self):
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "pages"
            result = self.run_offline_command(
                '    yield scrapy.Request("data:text/html,%3Ctextarea%20id%3D%22content%22%3E'
                'offline%20wiki%3C%2Ftextarea%3E", callback=self.parse_edit_page, '
                'cb_kwargs={"title": "Page"}, dont_filter=True)', output,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("offline wiki", (output / "Page.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
