
# app.py

import os
import re
import logging
import feedparser
import requests
from collections import deque
from datetime import datetime
from typing import List, Dict, Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.job import Job
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from dotenv import load_dotenv

# --------------------- Setup & Config ---------------------
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# Optional APIs
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
BING_NEWS_KEY = os.getenv("BING_NEWS_KEY")

# Poll interval
POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "10"))

# --------------------- Sources ---------------------
RSS_FEEDS: List[str] = [
    # National / General
    "https://www.thehindu.com/news/national/feeder/default.rss",
    "https://indianexpress.com/section/india/feed/",
    "https://www.deccanherald.com/rss.xml?type=india",
    "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml",
    # Business / Markets / Economy
    "https://www.business-standard.com/rss/home_page_top_stories.rss",
    "https://www.moneycontrol.com/rss/MCtopnews.xml",
    "https://www.livemint.com/rss/news",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://www.financialexpress.com/feed/",
    "https://www.cnbctv18.com/news/rss/",
    # Bengaluru / Karnataka
    "https://www.deccanherald.com/rss.xml?type=city",
    "https://www.deccanherald.com/rss.xml?type=karnataka",
    "https://bangaloremirror.indiatimes.com/rss.cms",
    "https://www.thehindu.com/news/cities/bangalore/feeder/default.rss",
    "https://www.newindianexpress.com/cities/bengaluru/rssfeed/?id=338&getXmlFeed=true",
]

# NewsAPI domain restriction (if NEWSAPI_KEY provided)
NEWSAPI_DOMAINS = ",".join([
    "thehindu.com",
    "indianexpress.com",
    "deccanherald.com",
    "hindustantimes.com",
    "business-standard.com",
    "moneycontrol.com",
    "livemint.com",
    "economictimes.indiatimes.com",
    "financialexpress.com",
    "cnbctv18.com",
    "bangaloremirror.indiatimes.com",
    "newindianexpress.com",
])

# --------------------- Keywords ---------------------
KEYWORDS: List[str] = [
    # Geography & civic
    r"\bBengaluru\b", r"\bBangalore\b", r"\bKarnataka\b", r"\bNamma Metro\b",
    r"\bBBMP\b", r"\bBMRCL\b", r"\btraffic\b", r"\bwater supply\b", r"\bflood\b",
    # Business/finance/economy
    r"\bacquisition\b", r"\bmerger\b", r"\bIPO\b", r"\bfunding\b",
    r"\bRBI\b", r"\binterest rate\b", r"\binflation\b",
    r"\bstock (surge|crash|fall|plunge|rally)\b",
    # Tech/startups/IT
    r"\bstartup\b", r"\bunicorn\b", r"\bAI\b", r"\bSaaS\b", r"\bdeeptech\b",
    r"\bIT services\b", r"\bInfosys\b", r"\bWipro\b", r"\bTCS\b",
    # Kannada (optional)
    r"\bಬೆಂಗಳೂರು\b", r"\bಕರ್ನಾಟಕ\b", r"\bಮೆಟ್ರೋ\b", r"\bಹೂಡಿಕೆ\b", r"\bಸ್ಟಾರ್ಟಪ್\b",
]

# --------------------- De-duplication ---------------------
SEEN_IDS: set[str] = set()

def stable_id_from(title: str, link: str) -> str:
    base = (title or "") + (link or "")
    return re.sub(r"\s+", "", base.strip().lower())[:256]

def matches_keywords(text: str) -> bool:
    if not text:
        return False
    for pattern in KEYWORDS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False

# --------------------- In-memory Alerts (replace webhook) ---------------------
ALERTS_CAPACITY = int(os.getenv("ALERTS_CAPACITY", "500"))
ALERTS: deque[Dict[str, Any]] = deque(maxlen=ALERTS_CAPACITY)

def store_alert(title: str, summary: str, link: str, source: str, published: str):
    ALERTS.appendleft({
        "title": title,
        "summary": summary,
        "link": link,
        "source": source,
        "published": published,
        "matched_at": datetime.now().isoformat(),
    })
    logging.info(f"Stored alert: {title} | {source}")

# --------------------- Fetchers ---------------------
def process_rss_feed(feed_url: str):
    try:
        logging.info(f"Fetching RSS: {feed_url}")
        feed = feedparser.parse(feed_url)
        source = feed.feed.get("title", "Unknown Source")
        for entry in feed.entries:
            title = entry.get("title", "") or ""
            summary = entry.get("summary", "") or ""
            link = entry.get("link", "") or ""
            published = entry.get("published", "Unknown")
            uid = stable_id_from(title, link)
            if uid in SEEN_IDS:
                continue
            text = f"{title}\n{summary}"
            if matches_keywords(text):
                SEEN_IDS.add(uid)
                store_alert(title, summary, link, source, published)
    except Exception as e:
        logging.error(f"RSS fetch failed for {feed_url}: {e}")

def fetch_newsapi_articles():
    if not NEWSAPI_KEY:
        return []
    try:
        logging.info("Querying NewsAPI...")
        query = (
            '("Bengaluru" OR "Bangalore" OR "Karnataka" OR India) AND '
            '(traffic OR "water supply" OR flood OR BBMP OR BMRCL OR Metro OR '
            'acquisition OR merger OR IPO OR funding OR RBI OR "interest rate" OR inflation OR '
            '"stock crash" OR "stock surge" OR rally OR startup OR unicorn OR AI OR SaaS OR Infosys OR Wipro OR TCS)'
        )
        params = {
            "q": query,
            "language": "en",
            "pageSize": 50,
            "sortBy": "publishedAt",
            "apiKey": NEWSAPI_KEY,
            "domains": NEWSAPI_DOMAINS
        }
        r = requests.get("https://newsapi.org/v2/everything", params=params, timeout=15)
        r.raise_for_status()
        return r.json().get("articles", [])
    except Exception as e:
        logging.error(f"NewsAPI fetch failed: {e}")
        return []

def process_newsapi():
    for a in fetch_newsapi_articles():
        title = a.get("title", "") or ""
        description = a.get("description", "") or ""
        url = a.get("url", "") or ""
        source = (a.get("source") or {}).get("name", "Unknown")
        published_at = a.get("publishedAt", "Unknown")
        uid = stable_id_from(title, url)
        if uid in SEEN_IDS:
            continue
        text = f"{title}\n{description}"
        if matches_keywords(text):
            SEEN_IDS.add(uid)
            store_alert(title, description, url, source, published_at)

def fetch_bing_news():
    if not BING_NEWS_KEY:
        return []
    try:
        logging.info("Querying Bing News (en-IN)...")
        endpoint = "https://api.cognitive.microsoft.com/bing/v7.0/news/search"
        query = (
            '("Bengaluru" OR "Bangalore" OR "Karnataka" OR India) '
            'AND (traffic OR "water supply" OR flood OR BBMP OR BMRCL OR Metro OR '
            'acquisition OR merger OR IPO OR funding OR RBI OR "interest rate" OR inflation OR '
            '"stock crash" OR "stock surge" OR rally OR startup OR unicorn OR AI OR SaaS OR Infosys OR Wipro OR TCS)'
        )
        params = {
            "q": query,
            "mkt": "en-IN",
            "count": 50,
            "sortBy": "Date",
            "freshness": "Day",
        }
        headers = {"Ocp-Apim-Subscription-Key": BING_NEWS_KEY}
        r = requests.get(endpoint, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json().get("value", [])
    except Exception as e:
        logging.error(f"Bing News fetch failed: {e}")
        return []

def process_bing_news():
    for item in fetch_bing_news():
        name = item.get("name", "") or ""
        desc = item.get("description", "") or ""
        url = item.get("url", "") or ""
        provider = item.get("provider", [])
        source_name = provider[0]["name"] if provider else "Unknown"
        date_published = item.get("datePublished", "Unknown")
        uid = stable_id_from(name, url)
        if uid in SEEN_IDS:
            continue
        text = f"{name}\n{desc}"
        if matches_keywords(text):
            SEEN_IDS.add(uid)
            store_alert(name, desc, url, source_name, date_published)

# --------------------- Service + Scheduler ---------------------
class NewsFeederService:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.job_id = "poll_job"
        self.is_started = False

    def poll_once(self):
        logging.info("Starting one-off news poll...")
        for url in RSS_FEEDS:
            process_rss_feed(url)
        if NEWSAPI_KEY:
            process_newsapi()
        if BING_NEWS_KEY:
            process_bing_news()
        logging.info("One-off poll complete.")

    def start_interval(self, minutes: int = POLL_INTERVAL_MINUTES):
        if self.scheduler.get_job(self.job_id):
            self.scheduler.reschedule_job(self.job_id, trigger="interval", minutes=minutes)
            logging.info(f"Rescheduled job to every {minutes} minutes.")
            return
        self.scheduler.add_job(self.poll_once, "interval", minutes=minutes, id=self.job_id, next_run_time=datetime.now())
        self.scheduler.start()
        self.is_started = True
        logging.info(f"Scheduler started. Polling every {minutes} minutes.")

    def stop_interval(self):
        job = self.scheduler.get_job(self.job_id)
        if job:
            self.scheduler.remove_job(self.job_id)
            logging.info("Interval job removed.")
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logging.info("Scheduler stopped.")
        self.is_started = False

    def status(self) -> Dict[str, Any]:
        job: Optional[Job] = self.scheduler.get_job(self.job_id)
        return {
            "started": self.is_started,
            "interval_minutes": POLL_INTERVAL_MINUTES,
            "job_exists": job is not None,
            "next_run_time": job.next_run_time.isoformat() if job and job.next_run_time else None,
            "feeds_count": len(RSS_FEEDS),
            "keywords_count": len(KEYWORDS),
            "seen_count": len(SEEN_IDS),
            "alerts_count": len(ALERTS),
            "newsapi_enabled": bool(NEWSAPI_KEY),
            "bing_enabled": bool(BING_NEWS_KEY),
        }

service = NewsFeederService()

# --------------------- FastAPI ---------------------
app = FastAPI(title="India/Bengaluru News Feeder", version="1.1.0", description="News alerts API (no webhook)")

class FeedsUpdate(BaseModel):
    feeds: List[str]

class KeywordsUpdate(BaseModel):
    keywords: List[str]

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

@app.get("/status")
def get_status():
    return service.status()

@app.post("/poll")
def poll_now():
    service.poll_once()
    return {"message": "Poll executed", "alerts_count": len(ALERTS)}

@app.post("/start")
def start(minutes: Optional[int] = None):
    m = minutes or POLL_INTERVAL_MINUTES
    service.start_interval(m)
    return {"message": f"Scheduler started/rescheduled for every {m} minutes", "status": service.status()}

@app.post("/stop")
def stop():
    service.stop_interval()
    return {"message": "Scheduler stopped", "status": service.status()}

# ---- Feeds management ----
@app.get("/feeds")
def list_feeds():
    return {"feeds": RSS_FEEDS}

@app.post("/feeds")
def set_feeds(update: FeedsUpdate):
    global RSS_FEEDS
    RSS_FEEDS = update.feeds
    return {"message": "Feeds updated", "feeds": RSS_FEEDS}

@app.post("/feeds/add")
def add_feed(url: str):
    if url in RSS_FEEDS:
        raise HTTPException(status_code=400, detail="Feed already present")
    RSS_FEEDS.append(url)
    return {"message": "Feed added", "feeds": RSS_FEEDS}

@app.delete("/feeds/remove")
def remove_feed(url: str):
    try:
        RSS_FEEDS.remove(url)
        return {"message": "Feed removed", "feeds": RSS_FEEDS}
    except ValueError:
        raise HTTPException(status_code=404, detail="Feed not found")

# ---- Keyword management ----
@app.get("/keywords")
def list_keywords():
    return {"keywords": KEYWORDS}

@app.post("/keywords")
def set_keywords(update: KeywordsUpdate):
    global KEYWORDS
    KEYWORDS = update.keywords
    return {"message": "Keywords updated", "keywords": KEYWORDS}

@app.post("/keywords/add")
def add_keyword(pattern: str):
    if pattern in KEYWORDS:
        raise HTTPException(status_code=400, detail="Keyword already present")
    KEYWORDS.append(pattern)
    return {"message": "Keyword added", "keywords": KEYWORDS}

@app.delete("/keywords/remove")
def remove_keyword(pattern: str):
    try:
        KEYWORDS.remove(pattern)
        return {"message": "Keyword removed", "keywords": KEYWORDS}
    except ValueError:
        raise HTTPException(status_code=404, detail="Keyword not found")

# ---- Alerts (new) ----
@app.get("/alerts")
def list_alerts(
    limit: int = Query(50, ge=1, le=ALERTS_CAPACITY),
    source: Optional[str] = None,
    contains: Optional[str] = None,
):
    items = list(ALERTS)
    if source:
        items = [a for a in items if a.get("source") == source]
    if contains:
        s = contains.lower()
        items = [a for a in items if s in (a.get("title","")+a.get("summary","")).lower()]
    return {"count": len(items), "alerts": items[:limit]}

@app.delete("/alerts")
def clear_alerts():
    ALERTS.clear()
    return {"message": "Alerts cleared"}

# ---- Debug: seen IDs ----
@app.get("/seen")
def list_seen(limit: int = 50):
    items = list(SEEN_IDS)[:limit]
    return {"count": len(SEEN_IDS), "sample": items}
