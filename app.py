
# main.py
import os
import asyncio
import time
import uuid
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

# -------------------------------------------------------------
# Reactor: install AsyncioSelectorReactor BEFORE importing Scrapy/Twisted
# -------------------------------------------------------------
os.environ.pop("TWISTED_REACTOR", None)

from twisted.internet import asyncioreactor
asyncioreactor.install(asyncio.get_event_loop())

from twisted.internet import reactor
from twisted.internet import error as terror  # ConnectionDone, ConnectionLost

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
import httpx  # for ping
import scrapy
from scrapy.crawler import CrawlerRunner
from scrapy import signals

app = FastAPI(title="FastAPI + Scrapy (Asyncio Reactor, Job-based, Stats)")

# -------------------------------------------------------------
# Scrapy base settings
# -------------------------------------------------------------
BASE_SETTINGS = {
    "ROBOTSTXT_OBEY": True,             # can be overridden per run
    "DOWNLOAD_DELAY": 0.10,
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
    "REACTOR_THREADPOOL_MAXSIZE": 20,
}

print("Twisted reactor in use:", reactor.__class__)

# -------------------------------------------------------------
# Helpers
# -------------------------------------------------------------
def stop_crawler_safely(crawler):
    try:
        crawler.stop()
    except Exception:
        pass

def validate_url_or_400(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Provide a full URL, e.g., https://example.com")
    return url

# -------------------------------------------------------------
# Collect items and responses via signals
# -------------------------------------------------------------
class ItemCollector:
    """Collect items emitted by spiders (post-pipeline) via Scrapy signals."""
    def __init__(self):
        self.items: List[Dict] = []
        self.responses: List[Dict[str, Any]] = []  # url + status + is_robot

    def connect(self, crawler):
        crawler.signals.connect(self._item_scraped, signal=signals.item_scraped)
        crawler.signals.connect(self._response_received, signal=signals.response_received)

    def _item_scraped(self, item, response, spider):
        try:
            self.items.append(dict(item))
        except Exception:
            self.items.append(item)

    def _response_received(self, response, request, spider):
        # Mark if this was robots.txt to help diagnose page_limit usage
        self.responses.append({
            "url": response.url,
            "status": response.status,
            "is_robots": response.url.endswith("/robots.txt"),
        })

# -------------------------------------------------------------
# Quotes spider (Scrapy ≥ 2.13 using async start())
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

    async def start(self):
        base = "https://quotes.toscrape.com/"
        url = f"{base}tag/{self.tag}/" if self.tag else base
        yield scrapy.Request(url, callback=self.parse)

    # Backward-compat (Scrapy < 2.13)
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
# In-memory job store
# -------------------------------------------------------------
JOBS: Dict[str, Dict] = {}  # task_id -> { started, done, error, count, results, stats, responses }

def new_task_id() -> str:
    return uuid.uuid4().hex

# -------------------------------------------------------------
# Start quotes crawl (job-based)
# -------------------------------------------------------------
@app.post("/scrape-quotes/start")
async def scrape_quotes_start(
    tag: Optional[str] = Query(default=None, description="Filter quotes by tag, e.g., 'life'"),
    page_limit: int = Query(2, ge=1, le=100, description="Stop after N pages"),
    obey_robots: bool = Query(True, description="Respect robots.txt (set false to test faster)"),
    log_level: str = Query("INFO", description="Scrapy log level (INFO/DEBUG/WARNING)"),
    debug: bool = Query(False, description="If true, sets robots=False and page_limit=3 for diagnostics"),
):
    """
    Starts a quotes crawl job and returns task_id immediately.
    Use /scrape-quotes/status and /scrape-quotes/result to fetch progress/results.
    """
    # Debug mode: quick diagnosis (robots off + ensure at least 1 content page beyond robots)
    if debug:
        obey_robots = False
        page_limit = max(page_limit, 3)

    settings = {
        **BASE_SETTINGS,
        "LOG_LEVEL": log_level,
        "ROBOTSTXT_OBEY": obey_robots,
        "CLOSESPIDER_PAGECOUNT": page_limit,  # counts robots + content responses
    }
    runner = CrawlerRunner(settings=settings)

    collector = ItemCollector()
    crawler = runner.create_crawler(QuotesSpider)
    collector.connect(crawler)

    d = runner.crawl(crawler, tag=tag)
    d.addErrback(lambda f: f.trap(terror.ConnectionDone, terror.ConnectionLost))

    task_id = new_task_id()
    JOBS[task_id] = {
        "started": time.time(),
        "done": False,
        "error": None,
        "count": 0,
        "results": [],
        "responses": [],
        "stats": {},
        "params": {
            "tag": tag,
            "page_limit": page_limit,
            "obey_robots": obey_robots,
            "log_level": log_level,
            "debug": debug,
        },
    }

    async def finalize():
        try:
            fut = d.asFuture(asyncio.get_event_loop())
            await fut
            JOBS[task_id]["done"] = True
            JOBS[task_id]["results"] = collector.items
            JOBS[task_id]["count"] = len(collector.items)
            # Include Scrapy stats to understand why items=0
            JOBS[task_id]["stats"] = crawler.stats.get_stats() or {}
            JOBS[task_id]["responses"] = collector.responses
        except Exception as e:
            JOBS[task_id]["done"] = True
            JOBS[task_id]["error"] = str(e)
            JOBS[task_id]["results"] = collector.items
            JOBS[task_id]["count"] = len(collector.items)
            JOBS[task_id]["stats"] = crawler.stats.get_stats() or {}
            JOBS[task_id]["responses"] = collector.responses

    asyncio.create_task(finalize())

    return {"task_id": task_id, "message": "Crawl started", "params": JOBS[task_id]["params"]}

# -------------------------------------------------------------
# Job status & result endpoints
# -------------------------------------------------------------
@app.get("/scrape-quotes/status")
async def scrape_quotes_status(task_id: str = Query(...)):
    job = JOBS.get(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown task_id")
    elapsed = time.time() - job["started"]
    return {
        "task_id": task_id,
        "done": job["done"],
        "error": job["error"],
        "count": job["count"],
        "elapsed_sec": round(elapsed, 2),
        "params": job.get("params", {}),
    }

@app.get("/scrape-quotes/result")
async def scrape_quotes_result(task_id: str = Query(...)):
    job = JOBS.get(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown task_id")
    payload = {
        "done": job["done"],
        "error": job["error"],
        "count": job["count"],
        "results": job["results"],
        "stats": job.get("stats", {}),
        "responses": job.get("responses", []),
        "params": job.get("params", {}),
    }
    # If not done, return partial results + responses + stats to help diagnose
    return JSONResponse(status_code=200 if job["done"] else 206, content=payload)

# -------------------------------------------------------------
# Optional: quick connectivity test
# -------------------------------------------------------------
@app.get("/ping-website")
async def ping_website(
    url: str = Query("https://quotes.toscrape.com/", description="URL to fetch quickly"),
    timeout: float = Query(10.0, ge=1.0, le=60.0),
):
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            start = time.time()
            r = await client.get(url)
            elapsed = time.time() - start
            return {
                "url": url,
                "status": r.status_code,
                "final_url": str(r.url),
                "elapsed_sec": round(elapsed, 2),
                "content_type": r.headers.get("Content-Type"),
            }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ping error: {e}")

# -------------------------------------------------------------
# Reactor info
# -------------------------------------------------------------
@app.get("/reactor")
def reactor_info():
    return {"reactor": str(reactor.__class__)}
