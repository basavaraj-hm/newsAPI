
import sys
from twisted.internet import asyncioreactor
asyncioreactor.install()  # ✅ Must be first

from fastapi import FastAPI, Request, Response
from scrapy.spiders import Spider
from scrapy.crawler import CrawlerRunner
from twisted.internet import reactor, defer
import threading
from threading import Lock

app = FastAPI()
scraped_data = []
data_lock = Lock()

class QuotesSpider(Spider):
    name = "quotes"
    start_urls = ["http://quotes.toscrape.com"]

    def parse(self, response):
        for quote in response.css("div.quote"):
            item = {
                'text': quote.css('span.text::text').get(),
                'author': quote.css('small.author::text').get()
            }
            with data_lock:
                scraped_data.append(item)
            yield item

scraping_in_progress = False

@app.get("/scrape")
def scrape_quotes():
    global scraping_in_progress
    scraping_in_progress = True
    scraped_data.clear()
    runner = CrawlerRunner()

    @defer.inlineCallbacks
    def crawl():
        yield runner.crawl(QuotesSpider)
        scraping_in_progress = False
        reactor.stop()

    if not reactor.running:
        threading.Thread(target=lambda: crawl() or reactor.run()).start()
    else:
        threading.Thread(target=crawl).start()

    return {"message": "Scraping started"}

@app.get("/status")
def get_status():
    return {"scraping_in_progress": scraping_in_progress}

@app.get("/results")
def get_results():
    if scraping_in_progress:
        return {"message": "Scraping still in progress", "scraped_data": []}
    return {"scraped_data": scraped_data}


