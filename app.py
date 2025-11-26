
from typing import Optional
import asyncio
from urllib.parse import urlparse
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import JSONResponse
from scrapy.crawler import CrawlerRunner
from scrapy import signals
import scrapy
from twisted.internet import asyncioreactor, reactor
from twisted.internet import error as terror  # for ConnectionDone / ConnectionLost

# Install reactor BEFORE any Twisted/Scrapy imports (already done above if in main file)
# asyncioreactor.install(asyncio.get_event_loop())

app = FastAPI(title="FastAPI + Scrapy (Asyncio)")

SCRAPY_SETTINGS = {
    "ROBOTSTXT_OBEY": True,
    "DOWNLOAD_DELAY": 0.25,
    "CONCURRENT_REQUESTS": 8,
    "LOG_LEVEL": "INFO",
    "USER_AGENT": "Mozilla/5.0 (compatible; FastAPI-Scrapy/1.0; +https://example.com/contact)",
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
}
RUNNER = CrawlerRunner(settings=SCRAPY_SETTINGS)

class PageItem(scrapy.Item):
    url = scrapy.Field()
    title = scrapy.Field()
    h1 = scrapy.Field()
    h2 = scrapy.Field()
    h3 = scrapy.Field()
    links = scrapy.Field()

class ItemCollector:
    def __init__(self):
        self.items = []
    def connect(self, crawler):
        crawler.signals.connect(self._item_scraped, signal=signals.item_scraped)
    def _item_scraped(self, item, response, spider):
        try:
            self.items.append(dict(item))
        except Exception:
            self.items.append(item)

class SiteSpider(scrapy.Spider):
    name = "site_spider"
    def __init__(self, start_url: str, max_pages: int = 10, **kwargs):
        super().__init__(**kwargs)
        self.start_url = start_url
        self.max_pages = int(max_pages)
        self.seen = set()
        parsed = urlparse(start_url)
        self.base_netloc = parsed.netloc
        self.allowed_domains = [parsed.hostname] if parsed.hostname else []
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

def validate_url_or_400(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Query param 'url' must include scheme and host, e.g., https://example.com")
    return url

@app.get("/crawl")
async def crawl_site(
    request: Request,
    url: str = Query(..., description="Starting URL to crawl (e.g., https://example.com)"),
    max_pages: int = Query(10, ge=1, le=200, description="Max pages to visit"),
    timeout: float = Query(60.0, ge=1.0, le=300.0, description="Max seconds to wait"),
):
    # Return 400 on bad URL instead of 422
    url = validate_url_or_400(url)

    collector = ItemCollector()
    crawler = RUNNER.create_crawler(SiteSpider)
    collector.connect(crawler)

    try:
        d = RUNNER.crawl(crawler, start_url=url, max_pages=max_pages)
        # Swallow "clean close" connection errors to avoid noisy logs
        d.addErrback(lambda f: f.trap(terror.ConnectionDone, terror.ConnectionLost))

        fut = d.asFuture(asyncio.get_event_loop())
        # If the client disconnects, uvicorn cancels this task:
        await asyncio.wait_for(fut, timeout=timeout)
        return {"count": len(collector.items), "results": collector.items}

    except asyncio.TimeoutError:
        try:
            crawler.stop()
        except Exception:
            pass
        return JSONResponse(status_code=504, content={"error": f"Crawl timed out after {timeout} seconds"})

    except asyncio.CancelledError:
        # Client disconnected; stop the crawl and re-raise so ASGI handles it
        try:
            crawler.stop()
        except Exception:
            pass
        raise

    except Exception as e:
        try:
            crawler.stop()
        except Exception:
            pass
        return JSONResponse(status_code=500, content={"error": str(e)})
