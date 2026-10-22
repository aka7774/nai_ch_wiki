from pathlib import Path
from datetime import datetime

from seesawiki_back_up import state as checkpoint
from urllib.parse import quote, urlsplit, urlunsplit

import scrapy
from seesawiki_back_up.items import SeesawikiBackUpItem


WIKI_TOP = "https://seesaawiki.jp/nai_ch/"
WIKI_FEED = "https://seesaawiki.jp/nai_ch/site.rdf"
PAGE_PREFIX = "/nai_ch/d/"
# 2026-04-07 までに編集画面から取った本文 (題名.txt)。もう書き込まない
LEGACY_DIR = Path(__file__).resolve().parents[2] / "back_up"


class BackupSpider(scrapy.Spider):
    name = "backup"
    allowed_domains = ["seesaawiki.jp", "wiki.seesaa.jp"]
    # start_urls = ["http://seesaawiki.jp/"]
    def __init__(self, mode="full", previous=None, started=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.previous = previous or {"pages": {}}
        self.started = started or checkpoint.now()
        self.full = mode == "full"
        self.feed_ok = False
        self.failed = False
        self.gap = False
        self.feed_dates = {}
        self.saved = {}
        self.missing = set()

    async def start(self):
        yield self.request(WIKI_FEED, self.parse_feed)

    def request(self, url, callback):
        return scrapy.Request(url, callback, errback=self.request_failed,
                              meta={"handle_httpstatus_list": [404]})

    def request_failed(self, failure):
        self.failed = True
        self.logger.error("Wiki request failed; checkpoint retained")

    def full_requests(self):
        yield self.request(WIKI_TOP, self.parse_page)
        for page_url in sorted(set(self.known_page_urls()) | set(self.previous["pages"])):
            yield self.request(page_url, self.parse_page)

    def known_page_urls(self):
        sources = [(LEGACY_DIR, "*.txt")]
        if getattr(self, "save_dir", None):
            sources.append((Path(self.save_dir), "*.html"))
        titles = set()
        for directory, pattern in sources:
            for path in directory.glob(pattern):
                titles.add(path.stem)
                # ファイル名では題名の "/" を "_" にしているので、元が "/" の場合も試す
                titles.add(path.stem.replace("_", "/"))
        urls = []
        for title in sorted(titles):
            try:
                # 記事の URL は EUC-JP の題名をパーセントエンコードしたもの ("/" はそのまま)
                encoded = quote(title.encode("euc_jp"), safe="/")
            except UnicodeEncodeError:
                continue
            if encoded:
                urls.append(f"https://seesaawiki.jp{PAGE_PREFIX}{encoded}")
        return urls

    def parse_feed(self, response):
        # Validate the entire feed before scheduling anything or advancing state.
        items = response.xpath('//*[local-name()="item"]')
        try:
            if response.status != 200 or not items:
                raise ValueError("empty feed")
            for item in items:
                link = item.xpath('./*[local-name()="link"]/text()').get("")
                date = item.xpath('./*[local-name()="date"]/text()').get("")
                url = self.page_url(response, link.strip())
                stamp = datetime.fromisoformat(date)
                if not url or stamp.tzinfo is None or stamp > datetime.fromisoformat(self.started):
                    raise ValueError("invalid feed metadata")
                self.feed_dates[url] = date
        except (ValueError, TypeError):
            self.failed = True
            self.logger.error("Invalid wiki feed metadata; checkpoint retained")
            return
        self.feed_ok = True
        last = self.previous.get("checked_at")
        # No overlap with the previous check means the bounded feed may have
        # discarded unseen edits. Recover with one full traversal, not silently.
        if last and min(map(datetime.fromisoformat, self.feed_dates.values())) > datetime.fromisoformat(last):
            self.gap = True
            self.full = True
            self.logger.warning("RSS coverage gap detected; recovering with full traversal")
        if self.full:
            yield from self.full_requests()
        for url, date in self.feed_dates.items():
            old = self.previous["pages"].get(url, {})
            if self.full or old.get("date") != date or not self.local_exists(old):
                yield self.request(url, self.parse_page)
        if not self.full:
            for url, old in self.previous["pages"].items():
                if url not in self.feed_dates and not old.get("missing") and not self.local_exists(old):
                    yield self.request(url, self.parse_page)

    def local_exists(self, entry):
        return bool(entry.get("file") and getattr(self, "save_dir", None)
                    and (Path(self.save_dir) / entry["file"]).is_file())

    def parse_page(self, response):
        if response.status == 404:
            self.missing.add(response.url)
            return
        # 記事の本文 (表示された HTML) を保存する
        title = "".join(response.css("#page-header .title h2::text").getall()).strip()
        body = response.css("#page-body div.user-area").get()
        if title and body:
            item = SeesawikiBackUpItem()
            item["title"] = title
            item["text"] = body
            item["url"] = response.url
            yield item
        else:
            self.failed = True
            self.logger.error("Wiki page body missing; checkpoint retained")
        # ほかの記事へのリンクをたどる (重複は Scrapy が除く)
        if not self.full:
            return
        for href in response.xpath("//a/@href").getall():
            page_url = self.page_url(response, href)
            if page_url:
                yield self.request(page_url, self.parse_page)

    @staticmethod
    def page_url(response, href):
        url = urlsplit(response.urljoin(href))
        if (
            url.scheme not in ("http", "https")
            or url.netloc != "seesaawiki.jp"
            or not url.path.startswith(PAGE_PREFIX)
            or url.path == PAGE_PREFIX
        ):
            return None
        return urlunsplit(("https", url.netloc, url.path, "", ""))
