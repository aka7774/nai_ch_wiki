import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from fivech_back_up.thread_backup import (
    ThreadBackupManager,
    ThreadMeta,
    normalize_thread_url,
    parse_search_results_html,
    parse_thread_url,
)


def make_payload(title: str, first_post_at: str, previous_url: str | None = None, post_count: int = 2) -> dict:
    first_body = ""
    if previous_url:
        first_body = f"※前スレ <br> {previous_url}"
    comments = [[1, "user", "sage", first_post_at, "id", "", first_body]]
    for idx in range(2, post_count + 1):
        comments.append([idx, "user", "", first_post_at, "id", "", ""])
    return {
        "thread": [0, post_count, "fate", "liveuranus/0", "", title, 1],
        "comments": comments,
    }


class ThreadBackupUrlTests(unittest.TestCase):
    def test_normalize_legacy_pc_url_to_current_domain(self) -> None:
        url = "https://fate.5ch.net/test/read.cgi/liveuranus/1678398509/"
        self.assertEqual(
            "https://fate.5ch.io/test/read.cgi/liveuranus/1678398509",
            normalize_thread_url(url),
        )

    def test_parse_itest_io_url_without_subdomain_uses_board_map(self) -> None:
        url = "https://itest.5ch.io/test/read.cgi/liveuranus/1772479750/"
        self.assertEqual(
            ("fate", "liveuranus", "1772479750"),
            parse_thread_url(url),
        )

    def test_parse_scheme_relative_thread_url(self) -> None:
        url = "//fate.5ch.io/test/read.cgi/liveuranus/1772479750"
        self.assertEqual(
            ("fate", "liveuranus", "1772479750"),
            parse_thread_url(url),
        )

    def test_parse_search_results_html_accepts_scheme_relative_io_links(self) -> None:
        html = """
        <div class="list_line">
            <a class="list_line_link" href="//fate.5ch.io/test/read.cgi/liveuranus/1772479750">
                <div class="list_line_link_title">なんJNVA部★623 (1002)</div>
            </a>
        </div>
        """
        self.assertEqual(
            [{
                "url": "https://fate.5ch.io/test/read.cgi/liveuranus/1772479750",
                "title": "なんJNVA部★623 (1002)",
            }],
            parse_search_results_html(html),
        )

    def test_discover_next_threads_filters_unrelated_search_results(self) -> None:
        with TemporaryDirectory() as tmpdir:
            manager = ThreadBackupManager(Path(tmpdir))
            manager.client = Mock()
            manager.client.search_threads.return_value = [
                {
                    "url": "https://nova.5ch.io/test/read.cgi/livegalileo/1773291405",
                    "title": "緊迫する中東情勢の中、ヨルダン政府が警告",
                },
                {
                    "url": "https://fate.5ch.io/test/read.cgi/liveuranus/1772000000",
                    "title": "なんJLLM部 ★6",
                },
                {
                    "url": "https://fate.5ch.io/test/read.cgi/liveuranus/1772865113",
                    "title": "なんJNVA部★629",
                },
            ]
            meta = ThreadMeta(
                dat_id="1772479750",
                url="https://fate.5ch.io/test/read.cgi/liveuranus/1772479750",
                normalized_url="https://fate.5ch.io/test/read.cgi/liveuranus/1772479750",
                number=628,
                title="なんJNVA部★628",
            )

            discovered = manager._discover_next_threads(meta)

            self.assertEqual(1, len(discovered))
            self.assertEqual("1772865113", discovered[0].dat_id)
            self.assertEqual(
                "https://fate.5ch.io/test/read.cgi/liveuranus/1772865113",
                meta.next_url,
            )

    def test_sync_latest_primary_threads_from_search_backfills_missing_threads(self) -> None:
        with TemporaryDirectory() as tmpdir, patch("fivech_back_up.thread_backup.time.sleep", return_value=None):
            manager = ThreadBackupManager(Path(tmpdir))
            manager.state["threads"] = {
                "1773831807": ThreadMeta(
                    dat_id="1773831807",
                    url="https://fate.5ch.io/test/read.cgi/liveuranus/1773831807",
                    normalized_url="https://fate.5ch.io/test/read.cgi/liveuranus/1773831807",
                    number=631,
                    title="なんJNVA部★631",
                    status="archived",
                    post_count=1002,
                ).to_dict()
            }
            manager.client = Mock()
            manager.client.search_threads.return_value = [
                {
                    "url": "https://nova.5ch.io/test/read.cgi/livegalileo/1773291405",
                    "title": "緊迫する中東情勢の中、ヨルダン政府が警告",
                },
                {
                    "url": "https://fate.5ch.io/test/read.cgi/liveuranus/1774260620",
                    "title": "なんJNVA部★632",
                },
                {
                    "url": "https://fate.5ch.io/test/read.cgi/liveuranus/1774527088",
                    "title": "なんJNVA部★633",
                },
            ]
            payloads = {
                "1774260620": make_payload(
                    "なんJNVA部★632",
                    "2026/03/23(月) 19:10:20.90",
                    previous_url="https://fate.5ch.io/test/read.cgi/liveuranus/1773831807/",
                    post_count=1002,
                ),
                "1774527088": make_payload(
                    "なんJNVA部★633",
                    "2026/03/26(木) 21:11:28.06",
                    previous_url="https://fate.5ch.io/test/read.cgi/liveuranus/1774260620/",
                    post_count=348,
                ),
            }
            manager.client.fetch_thread.side_effect = lambda _sub, _board, dat_id: payloads[dat_id]

            prefetched = manager._sync_latest_primary_threads_from_search()

            self.assertEqual({"1774260620", "1774527088"}, prefetched)
            self.assertIn("1774260620", manager.state["threads"])
            self.assertIn("1774527088", manager.state["threads"])
            self.assertEqual(
                "https://fate.5ch.io/test/read.cgi/liveuranus/1774260620",
                manager.state["threads"]["1774527088"]["previous_url"],
            )

    def test_run_daily_bootstraps_latest_thread_from_search_without_latest_url_file(self) -> None:
        with TemporaryDirectory() as tmpdir, patch("fivech_back_up.thread_backup.time.sleep", return_value=None):
            manager = ThreadBackupManager(Path(tmpdir))
            manager.client = Mock()
            manager.client.search_threads.return_value = [
                {
                    "url": "https://fate.5ch.io/test/read.cgi/liveuranus/1774527088",
                    "title": "なんJNVA部★633",
                },
            ]
            manager.client.fetch_thread.return_value = make_payload(
                "なんJNVA部★633",
                "2026/03/26(木) 21:11:28.06",
                post_count=348,
            )

            manager.run_daily(search_threshold=950)

            self.assertEqual(
                "https://fate.5ch.io/test/read.cgi/liveuranus/1774527088\n",
                manager.latest_url_path.read_text(encoding="utf-8"),
            )
            self.assertIn("1774527088", manager.state["threads"])


if __name__ == "__main__":
    unittest.main()
