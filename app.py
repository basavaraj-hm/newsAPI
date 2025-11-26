
# main.py
import os
import asyncio

# 0) Ensure env doesn't force a different reactor
os.environ.pop("TWISTED_REACTOR", None)

# 1) Install AsyncioSelectorReactor BEFORE any Twisted/Scrapy import
from twisted.internet import asyncioreactor
asyncioreactor.install(asyncio.get_event_loop())

# 2) Now import FastAPI/Scrapy/Twisted modules
from typing import Optional, List, Dict
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

import scrapy
from scrapy.crawler import CrawlerRunner
from scrapy import signals

from twisted.internet import reactor  # safe now
print("Twisted reactor in use:", reactor.__class__)

app = FastAPI(title="FastAPI + Scrapy (Asyncio reactor)")

# Scrapy settings aligned with the installed reactor
SCRAPY_SETTINGS = {
    "ROBOTSTXT_OBEY": True,
    "DOWNLOAD_DELAY": 0.25,
    "CONCURRENT_REQUESTS": 8,
    "LOG_LEVEL": "INFO",
    "USER_AGENT": "Mozilla/5.0 (compatible; FastAPI-Scrapy/1.0)",
    # Keep Scrapy’s expectation in sync with what we installed:
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
}

RUNNER = CrawlerRunner(settings=SCRAPY_SETTINGS)

# ---------- Example spider ----------
class QuoteItem(scrapy.Item):
    text = scrapy.Field()
    author = scrapy.Field()
    tags = scrapy.Field()
    source_url = scrapy.Field()

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
        for q in response.css("div.quote"):
            item = QuoteItem()
            item["text"] = q.css("span.text::text").get()
            item["author"] = q.css("small.author::text").get()
            item["tags"] = q.css("div.tags a.tag::text").getall()
            item["source_url"] = response.url
            yield item
        next_page = response.css("li.next a::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)

# ---------- Collect items via signals ----------
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

@app.get("/scrape-quotes")
async def scrape_quotes(
    tag: Optional[str] = Query(default=None, description="Filter quotes by tag, e.g., 'life'"),
    timeout: float = Query(30.0, ge=1.0, le=120.0),
):
    collector = ItemCollector()
    crawler = RUNNER.create_crawler(QuotesSpider)
    collector.connect(crawler)

    try:
        # RUNNER.crawl returns a Twisted Deferred → convert to asyncio Future
        d = RUNNER.crawl(crawler, tag=tag)
        fut = d.asFuture(asyncio.get_event_loop())
        await asyncio.wait_for(fut, timeout=timeout)
        return {"count": len(collector.items), "results": collector.items}
    except asyncio.TimeoutError:
        try: crawler.stop()
        except Exception: pass
        return JSONResponse(status_code=504, content={"error": f"Crawl timed out after {timeout} seconds"})
    except Exception as e:
        try: crawler.stop()
        except Exception: pass
