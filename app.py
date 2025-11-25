
from fastapi import FastAPI
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from my_spider import SimpleSpider
import asyncio

app = FastAPI()

@app.get("/scrape")
async def scrape(url: str):
    """
    Run Scrapy spider programmatically and return scraped data.
    """
    scraped_data = []

    def crawler_results(item):
        scraped_data.append(item)

    process = CrawlerProcess(get_project_settings())
    process.crawl(SimpleSpider, url=url)
    process.signals.connect(crawler_results, signal=scrapy.signals.item_scraped)

    # Run Scrapy in a thread to avoid blocking FastAPI
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, process.start)

