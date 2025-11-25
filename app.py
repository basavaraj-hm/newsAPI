
# app.py
import crochet
crochet.setup()  # Start Twisted reactor in a background thread (call once)

from typing import Optional, List, Dict
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

import scrapy
from scrapy.crawler import CrawlerRunner
from scrapy import signals
from twisted.internet import defer

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
        # Use item_scraped to collect items after pipelines
        crawler.signals.connect(self._item_scraped, signal=signals.item_scraped)

    def _item_scraped(self, item, response, spider):
        # Convert Item to dict
        try:
            self.items.append(dict(item))
        except Exception:
            # If item is already a dict
            self.items.append(item)

# ---------- FastAPI ----------
app = FastAPI(title="FastAPI + Scrapy (Single-file)")

SCRAPY_SETTINGS = {
    "ROBOTSTXT_OBEY": True,
    "DOWNLOAD_DELAY": 0.2,
    "CONCURRENT_REQUESTS": 8,
    "LOG_LEVEL": "INFO",
    # If you add pipelines, item_scraped is emitted AFTER pipelines run
    # "ITEM_PIPELINES": { "path.to.pipeline.Class": 300 },
}

RUNNER = CrawlerRunner(settings=SCRAPY_SETTINGS)

@app.get("/scrape")
def scrape_quotes(tag: Optional[str] = Query(default=None, description="Filter quotes by tag, e.g. 'life'")):
    collector = ItemCollector()

    @crochet.wait_for(timeout=30.0)  # Wait up to 30 seconds
    def _crawl(tag_arg: Optional[str]):
        crawler = RUNNER.create_crawler(QuotesSpider)
        collector.connect(crawler)
        d: defer.Deferred = RUNNER.crawl(crawler, tag=tag_arg)
        return d

    try:
        _crawl(tag_arg=tag)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    return {"count": len(collector.items), "results": collector.items}


