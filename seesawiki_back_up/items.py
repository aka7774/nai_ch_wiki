# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class SeesawikiBackUpItem(scrapy.Item):
    # define the fields for your item here like:
    # name = scrapy.Field()
    text = scrapy.Field()  # 抽出したテキスト
    title = scrapy.Field()  # 抽出したタイトル
    pass
