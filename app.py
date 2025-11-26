
# app.py
import asyncio
from twisted.internet import asyncioreactor
# IMPORTANT: install reactor BEFORE any Twisted/Scrapy import
asyncioreactor.install(asyncio.get_event_loop())

from typing import Optional, List, Dict
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

import scrapy
from scrapy.crawler import CrawlerRunner
from scrapy import signals
from twisted.internet.defer import ensureDeferred

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
        next_page = response.css("li.next a::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)

# ---------- Collector ----------
class ItemCollector:
    def __init__(self):
        self.items: List[Dict] = []
    def connect(self, crawler):
        crawler.signals.connect(self._item_scraped, signal=signals.item_scraped)
    def _item_scraped(self, item, response, spider):
        try:
            self.items.append(dict(item))
        except Exception:
            self.items.append(item)

# ---------- FastAPI ----------
app = FastAPI(title="FastAPI + Scrapy (Asyncio reactor)")

SCRAPY_SETTINGS = {
    "ROBOTSTXT_OBEY": True,
    "DOWNLOAD_DELAY": 0.2,
    "CONCURRENT_REQUESTS": 8,
    "LOG_LEVEL": "INFO",
    # Optional (align Scrapy’s setting with what we installed)
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
}

RUNNER = CrawlerRunner(settings=SCRAPY_SETTINGS)

@app.get("/scrape")
async def scrape_quotes(tag: Optional[str] = Query(default=None, description="Filter quotes by tag, e.g. 'life'")):
    collector = ItemCollector()
    crawler = RUNNER.create_crawler(QuotesSpider)
    collector.connect(crawler)

    try:
        # RUNNER.crawl returns a Deferred; ensureDeferred makes it awaitable
        await ensureDeferred(RUNNER.crawl(crawler, tag=tag))
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    return {"count": len(collector.items), "results": collector.items}
