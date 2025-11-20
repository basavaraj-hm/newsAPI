import scrapy

class QuotesSpider(scrapy.Spider):
    name = "quotes"
    start_urls = ["http://quotes.toscrape.com"]

    def parse(self, response):
        for quote in response.css("div.quote"):
           .crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from quotes_spider import QuotesSpider

app = FastAPI()

@app.get("/scrape")
def scrape_quotes():
    scraped_data = []

    # Define a custom pipeline to collect data
    class CollectPipeline:
        def process_item(self, item, spider):
            scraped_data.append(item)
            return item

    process = CrawlerProcess(settings={
        "LOG_ENABLED": False,
        "ITEM_PIPELINES": { '__main__.CollectPipeline': 1 }
    })

    process.crawl(QuotesSpider)
    process.start()  # Blocks until spider finishes

    return {"quotes": scraped_data}
