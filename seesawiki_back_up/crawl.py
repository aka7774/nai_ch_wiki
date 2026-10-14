import argparse
import pathlib
import sys

from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings


ROOT_DIR = pathlib.Path(__file__).parents[1].resolve()
# Allow the same entry point to be imported and run directly from gitpush.sh.
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from seesawiki_back_up import settings as project_settings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Back up SeesaaWiki pages.")
    parser.add_argument("spider", choices=["backup"])
    parser.add_argument("--save-dir", type=pathlib.Path, default=ROOT_DIR / "back_up")
    parser.add_argument("-s", "--set", action="append", default=[], metavar="NAME=VALUE")
    args = parser.parse_args(argv)

    settings = Settings()
    settings.setmodule(project_settings, priority="project")
    for setting in args.set:
        name, separator, value = setting.partition("=")
        if not separator or not name:
            parser.error("settings must have the form NAME=VALUE")
        settings.set(name, value, priority="cmdline")

    args.save_dir.mkdir(parents=True, exist_ok=True)
    process = CrawlerProcess(settings)
    crawler = process.create_crawler(args.spider)
    process.crawl(crawler, save_dir=str(args.save_dir.resolve()))
    process.start()

    saved_pages = crawler.stats.get_value("item_scraped_count", 0)
    if process.bootstrap_failed or saved_pages == 0:
        print("Wiki backup failed: no pages saved or crawler startup failed.", file=sys.stderr)
        return 1
    print(f"Wiki backup saved {saved_pages} pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
