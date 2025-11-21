from fastapi import FastAPI
from scrapy.crawler import CrawlerProcess
from scrapy.spiders import Spider
from scrapy import Request
import threading

app = FastAPI()
scraped_data = []

class QuotesSpider(Spider):
    name = "quotes"
    start_urls = ["http://quotes.toscrape.com"]

    
    def parse(self, response):
        item = {
            'title': response.css('h1::text').get(),
            'link': response.url
        }
        scraped_data.append(item)
        return item


@app.get("/scrape")
def scrape_quotes():
    scraped_data.clear()

    def run_spider():
        process = CrawlerProcess(settings={
            "LOG_ENABLED": False,
            "ITEM_PIPELINES": { "app.CollectPipeline": 1 }
        })
        process.crawl(QuotesSpider)
       aped_url": "http://quotes.toscrape.com", "data": scraped_data}

