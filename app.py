import sys
from twisted.internet import asyncioreactor
asyncioreactor.install()

import requests
from fastapi import FastAPI
import yfinance as yf
from twilio.rest import Client
from bs4 import BeautifulSoup
from nsepython import *
from apscheduler.schedulers.background import BackgroundScheduler
import time
import http.client, urllib.parse
import scrapy
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging
from twisted.internet.task import ensureDeferred
import json
from io import StringIO
from contextlib import redirect_stdout

app = FastAPI()

def fetch_price():
    try:
        symbol = "NIITLTD"
        data = nse_fno(symbol)
        last_price = data.get("priceInfo", {}).get("lastPrice", None)
        if last_price is not None:
            print(f"Last price of {symbol}: ₹{last_price}")
        else:
            print(f"'lastPrice' not found in priceInfo for {symbol}. Full priceInfo: {data.get('priceInfo')}")
        client = Client('AC81d4b9b02bcc2deb5580f9b988c17c04', '31a95eaf36ddbdcd8de51c32b94aca79')
        message = client.messages.create(
            body=f"Last price of {symbol}: ₹{last_price}",
            from_='whatsapp:+14155238886',
            to='whatsapp:+919538505753'
        )
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
    symbol = "RELIANCE"
    last_price = 2523.75
    print(f"Last price of {symbol}: ₹{last_price} at {time.strftime('%H:%M:%S')}")

@app.get("/newsautomate")
def news_automate():
    conn = http.client.HTTPSConnection('api.marketaux.com')
    params = urllib.parse.urlencode({
        'api_token': 'uaa7ghJ7d0D8HOYnEPafuj8gl9yROR7JRDKgXEPd',
        'symbols': 'SBIN,TSLA',
        'limit': 50,
    })
    conn.request('GET', '/v1/news/all?{}'.format(params))
    res = conn.getresponse()
    data = res.read()
    print(data.decode('utf-8'))
    return {
        "values": data
    }

@app.get("/whatsup")
def whatsup():
    client = Client('AC81d4b9b02bcc2deb5580f9b988c17c04', '31a95eaf36ddbdcd8de51c32b94aca79')
    message = client.messages.create(
        body="whats app message is delivered",
        from_='whatsapp:+14155238886',
        to='whatsapp:+919538505753'
    )
    return {
        "Message sent": message.sid
    }

@app.get("/newsgold")
def newsgold():
    try:
        url = 'https://www.google.com/search?q=gold+rate'
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        print("Status Code:", response.status_code)
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = soup.find_all('span')
        for i, span in enumerate(paragraphs, start=1):
            print(f"Span {i} text:", span.text)
    except requests.exceptions.RequestException as e:
        print("Connection failed:", e)

@app.get("/nseprice/{symbol}")
def nseprice(symbol: str):
    try:
        data = nse_fno(symbol)
        last_price = data.get("priceInfo", {}).get("lastPrice", None)
        if last_price is not None:
            print(f"Last price of {symbol}: ₹{last_price}")
        else:
            print(f"'lastPrice' not found in priceInfo for {symbol}. Full priceInfo: {data.get('priceInfo')}")
        return {
            symbol: data
        }
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")

# Scrapy Spider
class SimpleQuotesSpider(scrapy.Spider):
    name = "simple_quotes"
    start_urls = ["https://quotes.toscrape.com/"]
    custom_settings = {
        'LOG_LEVEL': 'INFO',
        'FEEDS': {
            'quotes.json': {'format': 'json', 'overwrite': True},
        },
        'TELNETCONSOLE_ENABLED': False
    }

    def parse(self, response):
        for quote in response.css("div.quote"):
            yield {
                "text": quote.css("span.text::text").get(),
                "author": quote.css("small.author::text").get(),
            }

# ✅ Corrected Scrapy integration
async def run_spider_and_get_results():
    """Runs the Scrapy spider and returns the scraped results."""
    configure_logging(install_root_handler=False)
    runner = CrawlerRunner()
    await ensureDeferred(runner.crawl(SimpleQuotesSpider))  # ✅ Correct usage

    with open("quotes.json", "r") as f:
        data = json.load(f)
    return data

@app.get("/scrape", summary="Scrape quotes from quotes.toscrape.com")
async def scrape_quotes():
    try:
        results = await run_spider_and_get_results()
        return {"status": "success", "data": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}



