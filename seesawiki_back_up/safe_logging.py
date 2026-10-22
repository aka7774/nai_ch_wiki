"""Do not interpolate archived bodies, including pipeline error paths."""
import logging
from scrapy.logformatter import LogFormatter


class MetadataLogFormatter(LogFormatter):
    def scraped(self, item, response, spider):
        return None

    def dropped(self, item, exception, response, spider):
        return {"level": logging.WARNING, "msg": "Wiki item dropped", "args": {}}

    def item_error(self, item, exception, response, spider):
        return {"level": logging.ERROR, "msg": "Wiki item save failed", "args": {}}
