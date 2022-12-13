import time

import scrapy
from seesawiki_back_up.items import SeesawikiBackUpItem


class BackupSpider(scrapy.Spider):
    name = "backup"
    allowed_domains = ["seesaawiki.jp"]
    # start_urls = ["http://seesaawiki.jp/"]
    def __init__(self, query="", rank=0, *args, **kwargs):
        super(BackupSpider, self).__init__(*args, **kwargs)

    def start_requests(self):
        yield scrapy.Request(
            "https://seesaawiki.jp/nai_ch/l/?p=0&order=lastupdate&on_desc=1", self.parse
        )

    def check_status(self, response, callback_obj, cb_kwargs):
        if response.status != 200:
            if cb_kwargs["failed_count"] > 3:
                # 取得諦め
                return
            time.sleep(60)
            cb_kwargs["failed_count"] += 1
            yield scrapy.Request(
                response.url,
                callback=callback_obj,
                cb_kwargs=cb_kwargs,
            )

    def parse(self, response, failed_count: int = 0):
        # 通信のチェック
        self.check_status(
            response, self.parse, cb_kwargs={"failed_count": failed_count}
        )

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
        next_pages = response.xpath("//li[@class='next']/a")[0]
        next_page_link = next_pages.attrib["href"]
        if next_page_link is not None:
            yield scrapy.Request(next_page_link, callback=self.parse)

    def parse_article_page(self, response, title: str, failed_count: int = 0):
        # 通信のチェック
        self.check_status(
            response,
            self.parse_article_page,
            cb_kwargs={"failed_count": failed_count, "title": title},
        )

        # 記事のページから編集ページをリンクを取得し移動
        edit_page_link = response.xpath("//li[@class='edit']/a[1]").attrib["href"]
        if edit_page_link is not None:
            # 編集がロックされている場合はスルー
            edit_page_link = response.urljoin(edit_page_link)
            yield scrapy.Request(
                edit_page_link,
                callback=self.parse_edit_page,
                cb_kwargs={"title": title},
            )

    def parse_edit_page(self, response, title: str, failed_count: int = 0):
        # 通信のチェック
        self.check_status(
            response,
            self.parse_edit_page,
            cb_kwargs={"failed_count": failed_count, "title": title},
        )

        item = SeesawikiBackUpItem()
        # 編集用のテキストを取得
        textarea = response.css("textarea#content::text")
        item["text"] = textarea.get()
        item["title"] = title
        yield item
