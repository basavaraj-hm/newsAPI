from fastapi import FastAPI
from scrapy.crawler import CrawlerProcess
from scrapy.spiders import Spider

app = FastAPI()

# ✅ Define the Scrapy spider
class QuotesSpider(Spider):
    name = "quotes"
    start_urls = ["http://quotes.toscrape.com"]

    def parse(self, response):
        for quote in response.css("div.quote"):
            text = quote.css("span.text::text").get()
            author = quote.css("small.author::text").get()
            yield {"text": text, "author": author}

@app.get("/scrape")
def scrape_quotes():
    scraped_data = []

    # ✅ Custom pipeline to collect items
    class CollectPipeline:
        def process_item(self, item, spider):
            scraped_data.append(item)
            # ✅ Configure and run Scrapy inside FastAPI
    process = CrawlerProcess(settings={
        "LOG_ENABLED": False,
        "ITEM_PIPELINES": { '__main__.CollectPipeline': 1 }
    })

    process.crawl(QuotesSpider)
    process.start()  # Blocks until spider finishes

    return {"scraped_url": "http://quotes.toscrape.com", "data": scraped_data}
