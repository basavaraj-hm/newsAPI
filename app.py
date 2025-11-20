from twisted.internet import asyncioreactor
asyncioreactor.install()

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
        'TELNETCONSOLE_ENABLED': False
    }

    ---------------- RUN SPIDER AND RETURN RESULTS ----------------
async def run_spider_and_get_results():
    configure_logging(install_root_handler=False)
    runner = CrawlerRunner()
    await ensureDeferred(runner.crawl(QuotesSpider))  # ✅ Correct usage

    # Read data from JSON file after spider completes
    with open("quotes.json", "r") as f:
        data = json.load(f)
    return data

# ---------------- FASTAPI ENDPOINT ----------------
@app.get("/scrape")
async def scrape_quotes():
    try:
        
        results = await run_spider_and_get_results()
        return {"status": "success", "data": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}
