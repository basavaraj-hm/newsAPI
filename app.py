from fastapi import FastAPI
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from twisted.internet import reactor
from typing import List, Dict

from my_spider import MySpider # Import your Scrapy spider

app = FastAPI()

# Store scraped data temporarily (in a real app, use a database)
scraped_data = []

class CustomCrawlerProcess(CrawlerProcess):
    def crawl(self, crawler_or_spidercls, *args, **kwargs):
        crawler = self.create_crawler(crawler_or_spidercls)
        # Attach a signal to store items in scraped_data
        crawler.signals.connect(self._item_scraped, signal=scrapy.signals.item_scraped)
        return super().crawl(crawler, *args, **kwargs)

    def _item_scraped(self, item, spider):
        scraped_data.append(dict(item))

@app.get("/scrape")
async def scrape_quotes():
    """Initiates the Scrapy spider to scrape quotes."""
    global scraped_data
    scraped_data = [] # Clear previous data
    settings = get_project_settings()
    process = CustomCrawlerProcess(settings)
    process.crawl(MySpider)
    # This runs the reactor in a non-blocking way for FastAPI
    reactor.callFromThread(process.start)
    return {"message": "Scraping initiated. Check /data after a short while."}

@app.get("/data", response_model=List[Dict])
async def get_scraped_data():
    """Returns the currently scraped data."""
    return scraped_data

# To run the FastAPI application:
# uvicorn main:app --reload
