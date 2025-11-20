from fastapi import FastAPI, Query
from scrapy.crawler import CrawlerProcess
from dynamic_spider import DynamicSpider

app = FastAPI()

@app.get("/scrape")
def scrape_dynamic(url: str = Query(..., description="URL to scrape")):
    scraped_data = []

    # Custom pipeline to collect items
    class CollectPipeline:
        def process_item(self, item, spider):
            scraped_data.append(item)
            return item

    # Configure and run Scrapy inside FastAPI
    process = CrawlerProcess(settings={
        "LOG_ENABLED": False,
        "ITEM_PIPELINES": { '__main__.CollectPipeline': 1 }
    })

    process.crawl(DynamicSpider, url=url)
    process.start()  # Blocks until spider finishes

    return {"scraped_url": url, "data": scraped_data}
