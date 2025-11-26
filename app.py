
# main.py
import os
import asyncio
from typing import Optional, List, Dict
from urllib.parse import urlparse

# -------------------------------------------------------------
# 1) Install AsyncioSelectorReactor BEFORE importing Twisted/Scrapy
# -------------------------------------------------------------
os.environ.pop("TWISTED_REACTOR", None)

from twisted.internet import asyncioreactor
asyncioreactor.install(asyncio.get_event_loop())

from twisted.internet import reactor
from twisted.internet import error as terror  # ConnectionDone, ConnectionLost

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse

import scrapy
from scrapy.crawler import CrawlerRunner
from scrapy import signals

app = FastAPI(title="FastAPI + Scrapy (Immediate Results)")

# -------------------------------------------------------------
# 2) Base Scrapy settings (polite, tweakable per request)
# -------------------------------------------------------------
BASE_SETTINGS = {
    "ROBOTSTXT_OBEY": True,             # set per request below
    "DOWNLOAD_DELAY": 0.10,             # small delay; reduce for faster
    "CONCURRENT_REQUESTS": 8,
    "LOG_LEVEL": "INFO",
    "USER_AGENT": "Mozilla/5.0 (compatible; FastAPI-Scrapy/1.0; +https://example.com/contact)",
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    "DOWNLOAD_TIMEOUT": 15,
    "DNS_TIMEOUT": 5,
    "RETRY_ENABLED": True,
    "RETRY_TIMES": 1,
    "RETRY_HTTP_CODES": [500, 502, 503, 504, 522, 524, 408, 429],
    "AUTOTHROTTLE_ENABLED": False,
    "REDIRECT_ENABLED": True,
    "TELNETCONSOLE_ENABLED": False,
}

print("Twisted reactor in use:", reactor.__class__)

# -------------------------------------------------------------
# 3) Item collector via Scrapy signal (post-pipeline)
# -------------------------------------------------------------
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

# -------------------------------------------------------------
# 4) Quotes spider (Scrapy ≥ 2.13 with async start())
#    first_hit=True => do NOT follow next_page (finish fast)
# -------------------------------------------------------------
class QuoteItem(scrapy.Item):
    text = scrapy.Field()
    author = scrapy.Field()
    tags = scrapy.Field()
    source_url = scrapy.Field()

class QuotesSpider(scrapy.Spider):
    name = "quotes"
    allowed_domains = ["quotes.toscrape.com"]

    def __init__(self, tag: Optional[str] = None, first_hit: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.tag = tag
        self.first_hit = first_hit

    async def start(self):
        base = "https://quotes.toscrape.com/"
        url = f"{base}tag/{self.tag}/" if self.tag else base
        yield scrapy.Request(url, callback=self.parse)

    # Backward-compat for Scrapy < 2.13
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

        # Only follow pagination when NOT first_hit
        if not self.first_hit:
            next_page = response.css("li.next a::attr(href)").get()
            if next_page:
                yield response.follow(next_page, callback=self.parse)

# -------------------------------------------------------------
# 5) Endpoint: return results on the first hit (blocking until done)
# -------------------------------------------------------------
@app.get("/scrape-quotes")
async def scrape_quotes(
    tag: Optional[str] = Query(default=None, description="Filter quotes by tag, e.g., 'life'"),
    first_hit: bool = Query(default=True, description="If true, only scrape the first page and return immediately"),
    obey_robots: bool = Query(default=True, description="Respect robots.txt (disable for faster first hit, if permitted)"),
    item_limit: int = Query(default=0, ge=0, le=100, description="Optional: stop after N items (0 = no cap)"),
    timeout: float = Query(default=30.0, ge=1.0, le=300.0, description="Max seconds to wait for this call"),
    log_level: str = Query(default="INFO", description="Scrapy log level"),
):
    """
    Returns quotes in the very first call:
    - first_hit=True: only the first page (no pagination), fast completion.
    - obey_robots: True for compliance; set False to skip robots.txt for speed (only if allowed).
    - item_limit: optional CLOSESPIDER_ITEMCOUNT for even faster completion.
    """
    # Build per-call settings
    settings = {
        **BASE_SETTINGS,
        "ROBOTSTXT_OBEY": obey_robots,
        "LOG_LEVEL": log_level,
    }
    if item_limit > 0:
        settings["CLOSESPIDER_ITEMCOUNT"] = item_limit

    # Use a fresh runner for per-request settings
    runner = CrawlerRunner(settings=settings)

    collector = ItemCollector()
    crawler = runner.create_crawler(QuotesSpider)
    collector.connect(crawler)

    try:
        # Start crawl: pass tag + first_hit flag
        d = runner.crawl(crawler, tag=tag, first_hit=first_hit)
        # Swallow benign close logs
        d.addErrback(lambda f: f.trap(terror.ConnectionDone, terror.ConnectionLost))

        fut = d.asFuture(asyncio.get_event_loop())
        await asyncio.wait_for(fut, timeout=timeout)

        return {"count": len(collector.items), "results": collector.items}

    except asyncio.TimeoutError:
        # Return partial results instead of 504
        try:
            crawler.stop()
        except Exception:
            pass
        return JSONResponse(
            status_code=206,  # Partial Content
            content={
                "partial": True,
                "message": f"Timed out after {timeout} seconds — returning items scraped so far.",
                "count": len(collector.items),
                "results": collector.items,
            },
        )

    except Exception as e:
        try:
            crawler.stop()
        except Exception:
            pass
        return JSONResponse(status_code=500, content={"error": str(e)})

# -------------------------------------------------------------
# 6) Health endpoint (optional)
# -------------------------------------------------------------
@app.get("/reactor")
def reactor_info():
    return {"reactor": str(reactor.__class__)}
