
# main.py
import asyncio
from urllib.parse import urlparse

# 1) Install AsyncioSelectorReactor BEFORE importing any Twisted/Scrapy modules
from twisted.internet import asyncioreactor
asyncioreactor.install(asyncio.get_event_loop())

from typing import Optional, List, Dict

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

import scrapy
from scrapy.crawler import CrawlerRunner
from scrapy import signals

# Optional: sanity check log
from twisted.internet import reactor
print("Twisted reactor in use:", reactor.__class__)

# ---------- Scrapy settings ----------
SCRAPY_SETTINGS = {
    "ROBOTSTXT_OBEY": True,
    "DOWNLOAD_DELAY": 0.25,
    "CONCURRENT_REQUESTS": 8,
    "LOG_LEVEL": "INFO",
    "USER_AGENT": "Mozilla/5.0 (compatible; FastAPI-Scrapy/1.0; +https://example.com/contact)",
    # Align Scrapy’s expectation with the reactor we installed:
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
}

RUNNER = CrawlerRunner(settings=SCRAPY_SETTINGS)

# ---------- Item collector ----------
class ItemCollector:
    """Collect items emitted by spiders (after pipelines) via signals."""
    def __init__(self):
        self.items: List[Dict] = []

    def connect(self, crawler):
        crawler.signals.connect(self._item_scraped, signal=signals.item_scraped)

    def _item_scraped(self, item, response, spider):
        try:
            self.items.append(dict(item))
        except Exception:
            self.items.append(item)

# ---------- Example spider: quotes.toscrape.com ----------
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

# ---------- Generic crawler spider ----------
class PageItem(scrapy.Item):
    url = scrapy.Field()
    title = scrapy.Field()
    h1 = scrapy.Field()
    h2 = scrapy.Field()
    h3 = scrapy.Field()
    links = scrapy.Field()

class SiteSpider(scrapy.Spider):
    """
    Crawl same-domain pages starting from start_url, up to max_pages.
    Extracts title, headings, and links per page.
    """
    name = "site_spider"

    def __init__(self, start_url: str, max_pages: int = 10, **kwargs):
        super().__init__(**kwargs)
        self.start_url = start_url
        self.max_pages = int(max_pages)
        self.seen = set()

        # Derive allowed_domains from the start URL
        parsed = urlparse(start_url)
        self.base_netloc = parsed.netloc
        self.allowed_domains = [parsed.hostname] if parsed.hostname else []

    def start_requests(self):
        yield scrapy.Request(self.start_url, callback=self.parse)

    def parse(self, response):
        # Avoid revisiting pages
        if response.url in self.seen:
            return
        self.seen.add(response.url)

        # Extract basic page data
        item = PageItem()
        item["url"] = response.url
        item["title"] = response.css("title::text").get()
        item["h1"] = [h.get().strip() for h in response.css("h1::text")]
        item["h2"] = [h.get().strip() for h in response.css("h2::text")]
        item["h3"] = [h.get().strip() for h in response.css("h3::text")]
        item["links"] = [response.urljoin(href) for href in response.css("a::attr(href)").getall()]
        yield item

        # Follow same-domain links until max_pages
        if len(self.seen) >= self.max_pages:
            return

        for href in response.css("a::attr(href)").getall():
            url = response.urljoin(href)
            netloc = urlparse(url).netloc
            if netloc == self.base_netloc and url not in self.seen:
                yield response.follow(url, callback=self.parse)

# ---------- FastAPI app ----------
app = FastAPI(title="FastAPI + Scrapy (Asyncio Reactor)")

@app.get("/reactor")
def reactor_info():
    return {"reactor": str(reactor.__class__)}

@app.get("/scrape-quotes")
async def scrape_quotes(
    tag: Optional[str] = Query(default=None, description="Filter quotes by tag, e.g., 'life'"),
    timeout: float = Query(30.0, ge=1.0, le=120.0)
):
    collector = ItemCollector()
    crawler = RUNNER.create_crawler(QuotesSpider)
    collector.connect(crawler)
    try:
        d = RUNNER.crawl(crawler, tag=tag)  # returns Twisted Deferred
        fut = d.asFuture(asyncio.get_event_loop())  # convert to asyncio Future
        await fut
        return {"count": len(collector.items), "results": collector.items}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/crawl")
async def crawl_site(
    url: str = Query(..., description="Starting URL to crawl"),
    max_pages: int = Query(10, ge=1, le=200, description="Max number of pages to visit"),
    timeout: float = Query(60.0, ge=1.0, le=300.0)
):
    collector = ItemCollector()
    crawler = RUNNER.create_crawler(SiteSpider)
    collector.connect(crawler)
    try:
        d = RUNNER.crawl(crawler, start_url=url, max_pages=max_pages)
        fut = d.asFuture(asyncio.get_event_loop())
        # Optional: enforce timeout
        await asyncio.wait_for(fut, timeout=timeout)
        return {"count": len(collector.items), "results": collector.items}
    except asyncio.TimeoutError:
        try:
            crawler.stop()
        except Exception:
            pass
        return JSONResponse(status_code=504, content={"error": f"Crawl timed out after {timeout} seconds"})
    except Exception as e:
