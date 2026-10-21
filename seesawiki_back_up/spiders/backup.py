from pathlib import Path
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
    def __init__(self, query="", rank=0, *args, **kwargs):
        super(BackupSpider, self).__init__(*args, **kwargs)

    async def start(self):
        # robots.txt は一覧 (/*/l/) と編集 (/*/e/) を禁じているので、
        # トップページと RSS から記事ページ (/nai_ch/d/) のリンクをたどる。
        yield scrapy.Request(WIKI_TOP, self.parse_page)
        yield scrapy.Request(WIKI_FEED, self.parse_feed)
        # どこからもリンクされていない記事も取れるように、前に保存した題名の記事ページも直接開く。
        # 消えた記事は 404 になり、何も保存しない
        for page_url in self.known_page_urls():
            yield scrapy.Request(page_url, self.parse_page)

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
        # RSS は最近更新された記事。どこからもリンクされていない新しい記事の入口にする
        for link in response.xpath('//*[local-name()="item"]/*[local-name()="link"]/text()').getall():
            page_url = self.page_url(response, link.strip())
            if page_url:
                yield scrapy.Request(page_url, callback=self.parse_page)

    def parse_page(self, response):
        # 記事の本文 (表示された HTML) を保存する
        title = "".join(response.css("#page-header .title h2::text").getall()).strip()
        body = response.css("#page-body div.user-area").get()
        if title and body:
            item = SeesawikiBackUpItem()
            item["title"] = title
            item["text"] = body
            yield item
        else:
            self.logger.warning("No wiki page body found: %s", response.url)
        # ほかの記事へのリンクをたどる (重複は Scrapy が除く)
        for href in response.xpath("//a/@href").getall():
            page_url = self.page_url(response, href)
            if page_url:
                yield scrapy.Request(page_url, callback=self.parse_page)

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
