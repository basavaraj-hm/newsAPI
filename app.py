from fastapi import FastAPI
from scrapy.crawler import CrawlerProcess
from scrapy.spiders import Spider
import threading

app = FastAPI()
scraped_data = []

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
            return item


@app.get("/scrape")
def scrape_quotes():
    scraped_data.clear()

    def run_spider():
        process = CrawlerProcess(settings={"LOG_ENABLED": False})
        process.crawl(QuotesSpider)
        process.start()  # ✅ Start the crawler

    thread = threading.Thread(target=run_spider)
    thread.start()
    thread.join()  # Wait for spider to finish

