
# main.py
import os
import asyncio
from typing import Optional, List, Dict
from urllib.parse import urlparse

# -------------------------------------------------------------
# 1) Install AsyncioSelectorReactor BEFORE importing Twisted/Scrapy
#    and ensure env var doesn't force a different reactor
# -------------------------------------------------------------
os.environ.pop("TWISTED_REACTOR", None)

from twisted.internet import asyncioreactor
asyncioreactor.install(asyncio.get_event_loop())

# Now it's safe to import Twisted/Scrapy/FastAPI
from twisted.internet import reactor
from twisted.internet import error as terror  # ConnectionDone, ConnectionLost

from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import JSONResponse

import scrapy
from scrapy.crawler import CrawlerRunner
from scrapy import signals


# -------------------------------------------------------------
# 2) FastAPI app and Scrapy settings
# -------------------------------------------------------------
app = FastAPI(title="FastAPI + Scrapy (Asyncio Reactor)")

SCRAPY_SETTINGS = {
    # Politeness & basics
    "ROBOTSTXT_OBEY": True,
    "DOWNLOAD_DELAY": 0.25,               # small delay to be polite
    "CONCURRENT_REQUESTS": 8,             # tune per site
    "LOG_LEVEL": "INFO",
    "USER_AGENT": "Mozilla/5.0 (compatible; FastAPI-Scrapy/1.0; +https://example.com/contact)",

    # Make Scrapy expect the same reactor we installed
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",

    # Timeouts & retries (optional tuning)
    "DOWNLOAD_TIMEOUT": 30,
    "RETRY_ENABLED": True,
    "RETRY_TIMES": 2,
    "RETRY_HTTP_CODES": [500, 502, 503, 504, 522, 524, 408, 429],

    # AutoThrottle (optional, helps avoid hammering servers)
    "AUTOTHROTTLE_ENABLED": True,
    "AUTOTHROTTLE_START_DELAY": 0.5,
    "AUTOTHROTTLE_MAX_DELAY": 30.0,
    "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,

    # Close spider if it runs too long (safety)
    "CLOSESPIDER_TIMEOUT": 300,

    # Allow redirects
    "REDIRECT_ENABLED": True,

    # Disable Telnet console
    "TELNETCONSOLE_ENABLED": False,

    # If you use pipelines/middlewares, declare them here:
    # "ITEM_PIPELINES": {
    #     "your_project.pipelines.YourPipeline": 300
    # },
    # "DOWNLOADER_MIDDLEWARES": {
    #     "scrapy.downloadermiddlewares.retry.RetryMiddleware": 550,
    # }
}

RUNNER = CrawlerRunner(settings=SCRAPY_SETTINGS)

print("Twisted reactor in use:", reactor.__class__)


# -------------------------------------------------------------
# 3) Helpers
# -------------------------------------------------------------
def stop_crawler_safely(crawler):
    try:
        crawler.stop()
    except Exception:
        pass

def validate_url_or_400(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail="Query param 'url' must include scheme and host, e.g., https://example.com"
        )
    return url


# -------------------------------------------------------------
# 4) Item collector via Scrapy signal (post-pipeline)
# -------------------------------------------------------------
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


# -------------------------------------------------------------
# 5) Quotes spider (Scrapy ≥ 2.13 with async start())
#    Keeps start_requests() for backward compatibility
# -------------------------------------------------------------
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

    # New Scrapy ≥ 2.13 entrypoint (async generator)
    async def start(self):
        base = "https://quotes.toscrape.com/"
        url = f"{base}tag/{self.tag}/" if self.tag else base
        yield scrapy.Request(url, callback=self.parse)

    # Backward compatibility for Scrapy < 2.13
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


# -------------------------------------------------------------
# 6) Generic site crawler spider (same-domain crawl)
#    Uses async start() and keeps start_requests() for compat
# -------------------------------------------------------------
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

        parsed = urlparse(start_url)
        self.base_netloc = parsed.netloc
        self.allowed_domains = [parsed.hostname] if parsed.hostname else []

    # New Scrapy ≥ 2.13 entrypoint (async generator)
    async def start(self):
        yield scrapy.Request(self.start_url, callback=self.parse)

    # Backward compatibility for Scrapy < 2.13
    def start_requests(self):
        yield scrapy.Request(self.start_url, callback=self.parse)

    def parse(self, response):
        if response.url in self.seen:
            return
        self.seen.add(response.url)

        item = PageItem()
        item["url"] = response.url
        item["title"] = response.css("title::text").get()
        item["h1"] = [h.get().strip() for h in response.css("h1::text")]
        item["h2"] = [h.get().strip() for h in response.css("h2::text")]
        item["h3"] = [h.get().strip() for h in response.css("h3::text")]
        item["links"] = [response.urljoin(href) for href in response.css("a::attr(href)").getall()]
        yield item

        if len(self.seen) >= self.max_pages:
            return

        for href in response.css("a::attr(href)").getall():
            url = response.urljoin(href)
            if urlparse(url).netloc == self.base_netloc and url not in self.seen:
                yield response.follow(url, callback=self.parse)


# -------------------------------------------------------------
# 7) FastAPI endpoints
# -------------------------------------------------------------
@app.get("/reactor")
def reactor_info():
    return {"reactor": str(reactor.__class__)}

@app.get("/scrape-quotes")
async def scrape_quotes(
    tag: Optional[str] = Query(default=None, description="Filter quotes by tag, e.g., 'life'"),
    timeout: float = Query(30.0, ge=1.0, le=120.0, description="Max seconds to wait"),
):
    collector = ItemCollector()
    crawler = RUNNER.create_crawler(QuotesSpider)
    collector.connect(crawler)

    try:
        # Scrapy returns a Deferred → trap clean-close errors, convert to Future, and await
        d = RUNNER.crawl(crawler, tag=tag)
        d.addErrback(lambda f: f.trap(terror.ConnectionDone, terror.ConnectionLost))

        fut = d.asFuture(asyncio.get_event_loop())
        await asyncio.wait_for(fut, timeout=timeout)

        return {"count": len(collector.items), "results": collector.items}

    except asyncio.TimeoutError:
        stop_crawler_safely(crawler)
        return JSONResponse(
            status_code=504,
            content={"error": f"Crawl timed out after {timeout} seconds"}
        )

    except asyncio.CancelledError:
        # Client disconnected; stop and re-raise
        stop_crawler_safely(crawler)
        raise

    except Exception as e:
        stop_crawler_safely(crawler)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/crawl")
async def crawl_site(
    request: Request,
    url: str = Query(..., description="Starting URL to crawl, e.g., https://example.com"),
    max_pages: int = Query(10, ge=1, le=200, description="Max pages to visit"),
    timeout: float = Query(60.0, ge=1.0, le=300.0, description="Max seconds to wait"),
):
    url = validate_url_or_400(url)

    collector = ItemCollector()
    crawler = RUNNER.create_crawler(SiteSpider)
    collector.connect(crawler)

    try:
        d = RUNNER.crawl(crawler, start_url=url, max_pages=max_pages)
        d.addErrback(lambda f: f.trap(terror.ConnectionDone, terror.ConnectionLost))

        fut = d.asFuture(asyncio.get_event_loop())
        await asyncio.wait_for(fut, timeout=timeout)

        return {"count": len(collector.items), "results": collector.items}

    except asyncio.TimeoutError:
        stop_crawler_safely(crawler)
        return JSONResponse(
            status_code=504,
            content={"error": f"Crawl timed out after {timeout} seconds"}
        )

    except asyncio.CancelledError:
        stop_crawler_safely(crawler)
        raise

    except Exception as e:
        stop_crawler_safely(crawler)
        return JSONResponse(status_code=500, content={"error": str(e)})
