
# app.py
import asyncio

# 1) Install AsyncioSelectorReactor BEFORE importing Twisted/Scrapy
from twisted.internet import asyncioreactor
asyncioreactor.install(asyncio.get_event_loop())

from typing import Optional, List, Dict
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

import scrapy
from scrapy.crawler import CrawlerRunner
from scrapy import signals

# (Optional) sanity check — confirm reactor in logs
from twisted.internet import reactor  # noqa: E402  (import after install)
print("Twisted reactor in use:", reactor.__class__)

# ---------- Scrapy spider ----------
class QuoteItem(scrapy.Item):
    text = scrapy.Field()
    author = scrapy.Field()
    tags = scrapy.Field()

class QuotesSpider(scrapy.Spider):
    name = "quotes"
    allowed_domains = ["quotes.toscrape.com"]

    def __init__(self, tag: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.tag = tag

    def start_requests(self):
        base = "https://quotes.toscrape.com/"
        url = f"{base}tag/{self.tag}/" if self.tag else base
        yield scrapy.Request(url, callback=self.parse)

    def parse(self, response):
        for quote in response.css("div.quote"):
            item = QuoteItem()
            item["text"] = quote.css("span.text::text").get()
            item["author"] = quote.css("small.author::text").get()
            item["tags"] = quote.css("div.tags a.tag::text").getall()
            yield item

        # follow pagination
        next_page = response.css("li.next a::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)

# ---------- Collector ----------
class ItemCollector:
    def __init__(self):
        self.items: List[Dict] = []

    def connect(self, crawler):
        # Collect items after pipelines using item_scraped signal
        crawler.signals.connect(self._item_scraped, signal=signals.item_scraped)

