import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scrapy.http import HtmlResponse, XmlResponse

from seesawiki_back_up.crawl import main
from seesawiki_back_up.items import SeesawikiBackUpItem
from seesawiki_back_up.pipelines import SeesawikiBackUpPipeline
from seesawiki_back_up.spiders.backup import BackupSpider


ROOT_DIR = Path(__file__).resolve().parents[1]


def response(html, url="https://seesaawiki.jp/nai_ch/d/Page"):
    return HtmlResponse(
        url,
        body=html.encode("utf-8"),
        encoding="utf-8",
    )


PAGE_HTML = """
<div id="page-header"><div class="title"><div class="inner"><h2>
Group/Page<a href="https://seesaawiki.jp/nai_ch/e/edit?id=1"><img alt="edit" /></a>
</h2></div></div></div>
<div id="page-body"><div id="page-body-inner">
<div class="user-area"><table><tr><td>prompt &amp; text</td></tr></table>
<a href="/nai_ch/d/Second#section">Second</a></div>
<div id="information-box"><a href="https://seesaawiki.jp/nai_ch/e/edit?id=1">Edit</a></div>
</div></div>
<div id="sub"><a href="https://seesaawiki.jp/nai_ch/d/Menu?x=1">Menu</a>
<a href="https://seesaawiki.jp/nai_ch/l/">List</a>
<a href="https://seesaawiki.jp/nai_ch/hist/Page">History</a>
<a href="https://seesaawiki.jp/other/d/Page">Other wiki</a>
<a href="https://seesaawiki.jp/nai_ch/d/">Empty</a></div>
"""


class WikiSpiderTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_yields_top_page_and_feed(self):
        spider = BackupSpider()
        requests = [request async for request in spider.start()]
        self.assertEqual(
            ["https://seesaawiki.jp/nai_ch/", "https://seesaawiki.jp/nai_ch/site.rdf"],
            [request.url for request in requests],
        )
        self.assertEqual([spider.parse_page, spider.parse_feed],
                         [request.callback for request in requests])

    def test_feed_yields_article_requests(self):
        spider = BackupSpider()
        feed = XmlResponse(
            "https://seesaawiki.jp/nai_ch/site.rdf",
            body=b"""<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns="http://purl.org/rss/1.0/">
<channel rdf:about="https://seesaawiki.jp/nai_ch/"><link>https://seesaawiki.jp/nai_ch/</link></channel>
<item rdf:about="https://seesaawiki.jp/nai_ch/d/New%a5%da"><link>https://seesaawiki.jp/nai_ch/d/New%a5%da</link></item>
</rdf:RDF>""",
        )
        requests = list(spider.parse_feed(feed))
        self.assertEqual(["https://seesaawiki.jp/nai_ch/d/New%a5%da"],
                         [request.url for request in requests])
        self.assertEqual(spider.parse_page, requests[0].callback)

    def test_page_body_is_saved_and_only_article_links_followed(self):
        spider = BackupSpider()
        results = list(spider.parse_page(response(PAGE_HTML)))
        item, *requests = results
        self.assertEqual("Group/Page", item["title"])
        self.assertTrue(item["text"].startswith('<div class="user-area">'))
        self.assertIn("prompt &amp; text", item["text"])
        self.assertNotIn("information-box", item["text"])
        self.assertEqual(
            ["https://seesaawiki.jp/nai_ch/d/Second",
             "https://seesaawiki.jp/nai_ch/d/Menu"],
            [request.url for request in requests],
        )
        self.assertTrue(all(request.callback == spider.parse_page for request in requests))

    def test_page_without_body_yields_no_item(self):
        results = list(BackupSpider().parse_page(response(
            '<a href="/nai_ch/d/Other">Other</a>'
        )))
        self.assertEqual(["https://seesaawiki.jp/nai_ch/d/Other"],
                         [request.url for request in results])

    def test_pipeline_writes_html_file(self):
        with TemporaryDirectory() as tmpdir:
            spider = BackupSpider()
            spider.save_dir = tmpdir
            item = SeesawikiBackUpItem(title="Group/Page", text="<div>body</div>")
            SeesawikiBackUpPipeline().process_item(item, spider)
            self.assertEqual(
                "<div>body</div>",
                (Path(tmpdir) / "Group_Page.html").read_text(encoding="utf-8"),
            )


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
                '    yield scrapy.Request("data:text/html,%3Cdiv%20id%3D%22page-header%22%3E'
                '%3Cdiv%20class%3D%22title%22%3E%3Ch2%3EPage%3C%2Fh2%3E%3C%2Fdiv%3E%3C%2Fdiv%3E'
                '%3Cdiv%20id%3D%22page-body%22%3E%3Cdiv%20class%3D%22user-area%22%3E'
                'offline%20wiki%3C%2Fdiv%3E%3C%2Fdiv%3E", callback=self.parse_page, '
                'dont_filter=True)', output,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                '<div class="user-area">offline wiki</div>',
                (output / "Page.html").read_text(encoding="utf-8"),
            )

if __name__ == "__main__":
    unittest.main()
