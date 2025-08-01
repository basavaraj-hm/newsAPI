from fastapi import FastAPI
import yfinance as yf
from twilio.rest import Client
import requests

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
    client = Client(account_sid, auth_token)
    message = client.messages.create(
    body='🚨 Alert: Your system has triggered an event!',
    from_='whatsapp:+14155238886',  # Twilio sandbox number
    to='whatsapp:+919886402374'     # Your verified WhatsApp number
    )
    return {
        "Message sent:", message.sid
    }
