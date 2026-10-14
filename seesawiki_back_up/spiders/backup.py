import scrapy
from seesawiki_back_up.items import SeesawikiBackUpItem


class BackupSpider(scrapy.Spider):
    name = "backup"
    allowed_domains = ["seesaawiki.jp", "wiki.seesaa.jp"]
    # start_urls = ["http://seesaawiki.jp/"]
    def __init__(self, query="", rank=0, *args, **kwargs):
        super(BackupSpider, self).__init__(*args, **kwargs)

    async def start(self):
        yield scrapy.Request(
            "https://seesaawiki.jp/nai_ch/l/?p=0&order=lastupdate&on_desc=1", self.parse
        )

    def parse(self, response):
        # HTTP エラーの再試行は Scrapy の RetryMiddleware に任せる。
        # 一覧のページからすべての記事のリンクを取得し移動
        links = response.xpath('//ul[@class="page-list"]/li/a')
        for link in links:
            page_link = link.attrib["href"]
            title = link.xpath("./text()").get()
            if page_link is not None:
                page_link = response.urljoin(page_link)
                yield scrapy.Request(
                    page_link,
                    callback=self.parse_article_page,
                    cb_kwargs={"title": title},
                )
        # 次の一覧が存在していたら取得
        next_page_link = response.xpath("//li[@class='next']/a/@href").get()
        if next_page_link:
            yield response.follow(next_page_link, callback=self.parse)

    def parse_article_page(self, response, title: str):
        # 記事のページから編集ページをリンクを取得し移動
        edit_page_link = response.xpath("//li[@class='edit']/a[1]/@href").get()
        if edit_page_link:
            # 編集がロックされている場合はスルー
            edit_page_link = response.urljoin(edit_page_link)
            yield scrapy.Request(
                edit_page_link,
                callback=self.parse_edit_page,
                cb_kwargs={"title": title},
            )

    def parse_edit_page(self, response, title: str):
        if not response.css("textarea#content"):
            self.logger.warning("No wiki editor found: %s", response.url)
            return
        item = SeesawikiBackUpItem()
        # 編集用のテキストを取得
        textarea = response.css("textarea#content::text")
        item["text"] = textarea.get(default="")
        item["title"] = title
        yield item
