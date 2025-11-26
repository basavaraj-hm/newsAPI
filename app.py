
# main.py
import os
import asyncio
from typing import Optional, List, Dict, Any

# -------------------------------------------------------------
# 1) Install AsyncioSelectorReactor BEFORE importing Twisted/Scrapy
# -------------------------------------------------------------
os.environ.pop("TWISTED_REACTOR", None)

from twisted.internet import asyncioreactor
asyncioreactor.install(asyncio.get_event_loop())

from twisted.internet import reactor
from twisted.internet import error as terror  # ConnectionDone, ConnectionLost

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

import scrapy
from scrapy.crawler import CrawlerRunner
from scrapy import signals

app = FastAPI(title="FastAPI + Scrapy (Immediate Results + Diagnostics)")

# -------------------------------------------------------------
# 2) Base Scrapy settings (polite; tweak per request below)
# -------------------------------------------------------------
BASE_SETTINGS = {
    "ROBOTSTXT_OBEY": True,             # can be overridden per call
    "DOWNLOAD_DELAY": 0.05,             # small delay; make 0.0 if you must be faster
    "CONCURRENT_REQUESTS": 8,
    "LOG_LEVEL": "INFO",
    "USER_AGENT": "Mozilla/5.0 (compatible; FastAPI-Scrapy/1.0; +https://example.com/contact)",
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    "DOWNLOAD_TIMEOUT": 10,             # per-request timeout
    "DNS_TIMEOUT": 5,
    "RETRY_ENABLED": True,
    "RETRY_TIMES": 1,
    "RETRY_HTTP_CODES": [500, 502, 503, 504, 522, 524, 408, 429],
    "AUTOTHROTTLE_ENABLED": False,
    "REDIRECT_ENABLED": True,
    "TELNETCONSOLE_ENABLED": False,
    "REACTOR_THREADPOOL_MAXSIZE": 20,

    # Good default request headers
    "DEFAULT_REQUEST_HEADERS": {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    },
}

print("Twisted reactor in use:", reactor.__class__)

# -------------------------------------------------------------
# 3) Collect items AND every response (url + status) for diagnostics
# -------------------------------------------------------------
class Collector:
    def __init__(self):
        self.items: List[Dict] = []
        self.responses: List[Dict[str, Any]] = []

    def connect(self, crawler):
        crawler.signals.connect(self._item_scraped, signal=signals.item_scraped)
        crawler.signals.connect(self._response_received, signal=signals.response_received)

    def _item_scraped(self, item, response, spider):
        try:
            self.items.append(dict(item))
        except Exception:
            self.items.append(item)

    def _response_received(self, response, request, spider):
        self.responses.append({
            "url": response.url,
            "status": response.status,
            "is_robots": response.url.endswith("/robots.txt"),
        })

# -------------------------------------------------------------
# 4) Quotes spider (Scrapy ≥ 2.13), first_hit controls pagination
# -------------------------------------------------------------
class QuoteItem(scrapy.Item):
    text = scrapy.Field()
    author = scrapy.Field()
    tags = scrapy.Field()
    source_url = scrapy.Field()

class QuotesSpider(scrapy.Spider):
    name = "quotes"
    allowed_domains = ["quotes.toscrape.com"]
    handle_httpstatus_all = True  # ensure we see non-200 responses in parse()

    def __init__(self, tag: Optional[str] = None, first_hit: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.tag = tag
        self.first_hit = first_hit

    async def start(self):
        base = "https://quotes.toscrape.com/"
        url = f"{base}tag/{self.tag}/" if self.tag else base
        yield scrapy.Request(url, callback=self.parse, dont_filter=True)

    # Backward-compat for Scrapy < 2.13
    def start_requests(self):
        base = "https://quotes.toscrape.com/"
        url = f"{base}tag/{self.tag}/" if self.tag else base
        yield scrapy.Request(url, callback=self.parse, dont_filter=True)

    def parse(self, response):
        # If non-200, expose status in logs and just return
        if response.status != 200:
            self.logger.warning(f"Non-200 status {response.status} for {response.url}")
            return

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
# 5) Endpoint: return results on the first hit + diagnostics
# -------------------------------------------------------------
@app.get("/scrape-quotes")
async def scrape_quotes(
    tag: Optional[str] = Query(default=None, description="Filter quotes by tag, e.g., 'life'"),
    first_hit: bool = Query(default=True, description="Only scrape the first page for a fast response"),
    obey_robots: bool = Query(default=False, description="Respect robots.txt (set to true for compliance)"),
    item_limit: int = Query(default=0, ge=0, le=100, description="Stop after N items (0 = no cap)"),
    timeout: float = Query(default=25.0, ge=5.0, le=300.0, description="Max seconds to wait"),
    log_level: str = Query(default="INFO", description="Scrapy log level"),
):
    """
    Returns quotes in the first call:
    - first_hit=True: scrape only the first page (no pagination).
    - obey_robots: default False here for speed; set True if required by policy.
    - item_limit: optional CloseSpider item cap for faster completion.
    - Includes diagnostics (responses + stats) so we can see why items might be 0.
    """
    settings = {
        **BASE_SETTINGS,
        "ROBOTSTXT_OBEY": obey_robots,
        "LOG_LEVEL": log_level,
    }
    if item_limit > 0:
        settings["CLOSESPIDER_ITEMCOUNT"] = item_limit

    runner = CrawlerRunner(settings=settings)

    collector = Collector()
    crawler = runner.create_crawler(QuotesSpider)
    collector.connect(crawler)

    try:
        d = runner.crawl(crawler, tag=tag, first_hit=first_hit)
        d.addErrback(lambda f: f.trap(terror.ConnectionDone, terror.ConnectionLost))
        fut = d.asFuture(asyncio.get_event_loop())
        await asyncio.wait_for(fut, timeout=timeout)

        # Always include diagnostics to understand 0-item cases
        return {
            "count": len(collector.items),
            "results": collector.items,
            "responses": collector.responses,
            "stats": crawler.stats.get_stats() or {},
            "params": {
                "tag": tag,
                "first_hit": first_hit,
                "obey_robots": obey_robots,
                "item_limit": item_limit,
                "timeout": timeout,
                "log_level": log_level,
            },
        }

    except asyncio.TimeoutError:
        try:
            crawler.stop()
        except Exception:
            pass
        return JSONResponse(
            status_code=206,  # Partial Content
            content={
                "partial": True,
                "message": f"Timed out after {timeout} seconds — returning diagnostics.",
                "count": len(collector.items),
                "results": collector.items,
                "responses": collector.responses,
                "stats": crawler.stats.get_stats() or {},
                "params": {
                    "tag": tag,
                    "first_hit": first_hit,
                    "obey_robots": obey_robots,
                    "item_limit": item_limit,
                    "timeout": timeout,
                    "log_level": log_level,
                },
            },
        )

    except Exception as e:
        try:
            crawler.stop()
        except Exception:
            pass
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "responses": collector.responses,
                "stats": crawler.stats.get_stats() or {},
            },
        )

# -------------------------------------------------------------
# 6) Reactor info
# -------------------------------------------------------------
@app.get("/reactor")
def reactor_info():
    return {"reactor": str(reactor.__class__)}
