import sys
from twisted.internet import asyncioreactor
asyncioreactor.install()

import requests
from fastapi import FastAPI
import scrapy
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging
from twisted.internet.task import ensureDeferred
import json

app = FastAPI()

# ---------------- SCRAPY SPIDER ----------------
class SimpleQuotesSpider(scrapy.Spider):
    name = "simple_quotes"
    start_urls = ["https://quotes.toscrape.com/"]
    custom_settings = {
        'LOG_LEVEL': 'INFO',
        'FEEDS': {
            'quotes.json': {'format': 'json', 'overwrite': True},
        },
        'TELNETCONSOLE_ENABLED': False  # ✅ Prevent Twisted Telnet issues
    }

    def parse(self, response):
        for quote in response.css("div.quote"):
            yield {
                "text": quote.css("span.text::text").get(),
                "author": quote.css("small.author::text").get()
            }

# ---------------- RUN SPIDER AND RETURN RESULTS ----------------
async        data = json.load(f)
    return data

# ---------------- FASTAPI ENDPOINT ----------------
@app.get("/scrape", summary="Scrape quotes from quotes.toscrape.com")
async def scrape_quotes():
    try:
        results = await run_spider_and_get_results()
        return {"status": "success", "data": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}
