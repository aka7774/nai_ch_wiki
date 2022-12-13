# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
import os

from itemadapter import ItemAdapter


class SeesawikiBackUpPipeline:
    def process_item(self, item, spider):
        # ファイル名に使用する文字列をエスケープする
        file_name = item["title"].replace("/", "_")
        # 保存先のディレクトリを指定する
        save_dir = spider.save_dir
        # for debug
        with open(os.path.join(save_dir, "00_got_title_list.txt"), "a+") as f:
            f.write(item["title"] + "\n")

        # ファイルが既に存在する場合は、上書きして保存する
        with open(os.path.join(save_dir, f"{file_name}.txt"), "w", encoding='utf-8') as f:
            f.write(item["text"])
        return item
