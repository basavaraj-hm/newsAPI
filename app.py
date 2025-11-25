
import asyncio
from fastapi import FastAPI
from scrapy.crawler import CrawlerRunner
from scrapy.spiders import Spider
from scrapy.utils.project import get_project_settings
from twisted.internet import reactor
from twisted.internet.defer import ensureDeferred
from threading import Thread

app = FastAPI()
scraped_data = []
scraping_in_progress = False

# Scrapy Spider
class QuotesSpider(Spider):
    name = "quotes"
    start_urls = ["http://quotes.toscrape.com"]

    def parse(self, response):
        for quote in response.css("div.quote"):
            item = {
                'text': quote.css('span.text::text').get(),
                'author': quote.css('small.author::text').get()
            }
            scraped_data.append(item)
            yield item

# Initialize CrawlerRunner
runner = CrawlerRunner(get_project_settings())

# Start Twisted reactor in a separate thread (only once)
def start_reactor():
    reactor.run(installSignalHandlers=False)

reactor_thread = Thread(target=start_reactor, daemon=True)
reactor_thread.start()

# Helper to run spider
async def run_spider():
    global scraping_in_progress
    scraping_in_progress = True
    scraped_data.clear()
    d = ensureDeferred(runner.crawl(QuotesSpider))
    await d
    scraping_in_progress = False

@app.get("/scrape")
async def scrape_quotes():
    if scraping_in_progress:
        return {"message": "Scraping already in progress"}
    await run_spider()
    return {"message": "Scraping completed", "scraped_data": scraped_data}

@app.get("/results")
def get_results():
    return {"scraping_in_progress": scraping_in_progress, "scraped_data": scraped_data}
