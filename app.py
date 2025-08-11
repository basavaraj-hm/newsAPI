import requests
from fastapi import FastAPI
import yfinance as yf
from twilio.rest import Client
from bs4 import BeautifulSoup


app = FastAPI()
def get_stock_price(symbol):
    stock = yf.Ticker(symbol)
    data = stock.history(period="1d", interval="1m")
    if not data.empty:
        return data['Close'].iloc[-1]
    return None

def get_news(symbol):
    url = f"https://newsapi.org/v2/everything?q={symbol}&sortBy=publishedAt&apiKey=fdf85b10d39a4f9f82f95ca9255ba43f"
    response = requests.get(url)
    articles = response.json().get("articles", [])
    return articles[:3]

@app.get("/alert/{symbol}")
def alert(symbol: str):
    price = get_stock_price(symbol)
    news = get_news(symbol)
    return {
        "symbol": symbol,
        "price": price,
        "news": news
    }
@app.get("/whatsup")
def whatsup():
    
    client = Client('AC81d4b9b02bcc2deb5580f9b988c17c04', '1ef448aa5bf253010ac7714cb2dbb60b')
    message = client.messages.create(
    body="whats app message is delevered",
    from_='whatsapp:+14155238886',  # Twilio sandbox number
    to='whatsapp:+919538505753'     # Your verified WhatsApp number
    )
    return {
        "Message sent:", message.sid
    }
@app.get("newsgold")
def newsgold():
    # URL of the gold rate page
    url = "https://www.goodreturns.in/gold-rates/"

    # Send a GET request
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")

    # Find the table containing gold rates
    table = soup.find("table", {"class": "gold_silver_table"})

    # Extract rows from the table
    rows = table.find_all("tr")

    # Print header
    return {
    print(f"{'City':<15} {'22K Gold (₹/10g)':<20} {'24K Gold (₹/10g)':<20}")
    }


