import scrapy

class QuotesSpider(scrapy.Spider):
    name = "quotes"
    start_urls = ["http://quotes.toscrape.com"]

    def parse(self, response):
        FastAPI()

@app.get("/quotes")
def get_quotes():
    with open("quotes.json", "r") as f:
        data = json.load(f)
    return {"quotes": data}
