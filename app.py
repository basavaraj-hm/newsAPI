
from fastapi import FastAPI
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

@app.get("/scrape")
def scrape_quotes():
    scraped_data.clear()
    runner = CrawlerRunner()

    @defer.inlineCallbacks
    def crawl():
        yield runner.crawl(QuotesSpider)
        reactor.stop()

    if not reactor.running:
        threading.Thread(target=lambda: crawl() or reactor.run()).start()
    else:
        threading.Thread(target=crawl).start()

    return {"message": "Scraping started", "scraped_url": "http://quotes.toscrape.com"}

@app.get("/results")
def get_results():
    with data_lock:
        return {"scraped_data": scraped_data}
