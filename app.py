
from fastapi import FastAPI, Request, Response
from twisted.internet import reactor, defer
import threading
from threading import Lock
from scrapy.spiders import Spider
from scrapy.crawler import CrawlerRunner

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

# ✅ Add HEAD support
@app.api_route("/results", methods=["GET", "HEAD"])
def get_results(request: Request):
    if request.method == "HEAD":
        # Return only status code for HEAD request
        return Response(status_code=200)
    with data_lock:
        return {"scraped_data": scraped_data}



