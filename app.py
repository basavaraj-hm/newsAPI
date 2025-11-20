from twisted.internet import asyncioreactor
asyncioreactor.install()  # Integrate Twisted with asyncio

from fastapi import FastAPI
import scrapy
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging
from twisted.internet.task import ensureDeferred
import json

app = FastAPI()

# ---------------- SCRAPY SPIDER ----------------
class QuotesSpider(scrapy.Spider):
    name = "quotes"
    start_urls = ["https://quotes.toscrape.com/"]
    custom_settings = {
        'LOG_LEVEL': 'INFO',
        'FEEDS': {
            'quotes.json': {'format': 'json', 'overwrite': True},
        },
        'TELNETCONSOLE_ENABLED': False  # Disable Telnet console
    }
    data from JSON file
    with open("quotes.json", "r") as f:
        data = json.load(f)
    twisted

