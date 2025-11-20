from fastapi import FastAPI
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from scrapy.utils.log import configure_logging
from twisted.internet import reactor
from typing import List, Dict
import json



app = FastAPI()

# In-memory storage for scraped data
scraped_data = []

class CustomPipeline:
    def process_item(self, item, spider):
        scraped_data.append(dict(item))
        return item

@app.get("/scrape", response_model=List[Dict])
async def scrape_quotes():
    global scraped_data
    scraped_data = [] # Clear previous data

    configure_logging({'LOG_LEVEL': 'INFO'})
    settings = get_project_settings()
    settings.set('ITEM_PIPELINES', {'main.CustomPipeline': 300}) # Add our custom pipeline

    process = CrawlerProcess(settings)
    process.crawl('quotes') # 'quotes' is the name of our spider

    # Run the reactor in a non-blocking way for FastAPI
    # This is a simplified approach; for production, consider a more robust way to manage Scrapy's reactor
    reactor.callFromThread(process.start)

    # Wait for a short period to allow scraping to begin (adjust as needed)
    # In a real application, you'd likely use a more sophisticated mechanism
    # to signal completion and retrieve results, e.g., a database or a queue.
    await reactor.callLater(5, lambda: None) # Wait 5 seconds

    return scraped_data

@app.get("/quotes", response_model=List[Dict])
async def get_quotes():
    return scraped_data

