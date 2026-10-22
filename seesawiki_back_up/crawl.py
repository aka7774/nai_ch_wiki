import argparse
import pathlib
import sys
import fcntl

from scrapy import signals
from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings


ROOT_DIR = pathlib.Path(__file__).parents[1].resolve()
# Allow the same entry point to be imported and run directly from gitpush.sh.
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from seesawiki_back_up import settings as project_settings
from seesawiki_back_up import state as checkpoint


def main(argv=None):
    parser = argparse.ArgumentParser(description="Back up SeesaaWiki pages.")
    parser.add_argument("spider", choices=["backup"])
    parser.add_argument("--save-dir", type=pathlib.Path, default=ROOT_DIR / "back_up_html")
    parser.add_argument("--mode", choices=["auto", "full", "incremental"], default="auto")
    parser.add_argument("-s", "--set", action="append", default=[], metavar="NAME=VALUE")
    args = parser.parse_args(argv)

    settings = Settings()
    settings.setmodule(project_settings, priority="project")
    for setting in args.set:
        name, separator, value = setting.partition("=")
        if not separator or not name:
            parser.error("settings must have the form NAME=VALUE")
        settings.set(name, value, priority="cmdline")

    # DEBUG includes response details from third-party middleware. The custom
    # formatter additionally removes item payloads at every log level.
    if settings.get("LOG_LEVEL").upper() == "DEBUG":
        settings.set("LOG_LEVEL", "INFO", priority="cmdline")
    settings.set("ROBOTSTXT_OBEY", True, priority="cmdline")
    settings.set("LOG_FORMATTER", "seesawiki_back_up.safe_logging.MetadataLogFormatter", priority="cmdline")
    args.save_dir.mkdir(parents=True, exist_ok=True)
    lock = (args.save_dir / ".crawl.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Wiki backup already running.", file=sys.stderr)
        lock.close()
        return 1
    try:
        return run(args, settings)
    finally:
        lock.close()


def run(args, settings):
    state_path = args.save_dir / ".crawl-state.json"
    try:
        previous = checkpoint.load(state_path)
    except (ValueError, OSError, KeyError, TypeError):
        print("Wiki checkpoint invalid; retained for recovery.", file=sys.stderr)
        return 1
    started = checkpoint.now()
    full = args.mode == "full" or (args.mode == "auto" and checkpoint.full_due(previous, started))
    # A new output needs a baseline even if incremental was explicitly chosen.
    full = full or not previous.get("full_at")
    process = CrawlerProcess(settings)
    crawler = process.create_crawler(args.spider)
    def item_failed(**kwargs):
        if crawler.spider is not None:
            crawler.spider.failed = True

    # Scrapy does not reliably count pipeline errors in its default stats.
    crawler.signals.connect(item_failed, signal=signals.item_error, weak=False)
    crawler.signals.connect(item_failed, signal=signals.item_dropped, weak=False)
    process.crawl(crawler, save_dir=str(args.save_dir.resolve()),
                  mode="full" if full else "incremental", previous=previous, started=started)
    process.start()
    spider = crawler.spider
    stats = crawler.stats.get_stats()
    saved_pages = stats.get("item_scraped_count", 0)
    failed = (process.bootstrap_failed or not spider or not spider.feed_ok or spider.failed
              or stats.get("finish_reason") != "finished"
              or any(value for key, value in stats.items()
                     if key.startswith(("spider_exceptions/", "item_error", "item_dropped")))
              or (spider.full and saved_pages == 0))
    if failed:
        print("Wiki backup failed: no pages saved or incomplete crawl; checkpoint retained.", file=sys.stderr)
        return 1
    pages = dict(previous["pages"])
    pages.update(spider.saved)
    for url in spider.missing:
        if url in pages:
            pages[url] = {**pages[url], "missing": True}
    state = {"pages": pages, "checked_at": started,
             "full_at": started if spider.full else previous["full_at"],
             "missing_urls": sorted(spider.missing), "coverage_gap": spider.gap}
    checkpoint.save(state_path, state)
    print(f"Wiki backup saved {saved_pages} pages; mode={'full' if spider.full else 'incremental'}; "
          f"missing={len(spider.missing)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
