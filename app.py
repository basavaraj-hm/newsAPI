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
    
    client = Client('AC81d4b9b02bcc2deb5580f9b988c17c04', 'f112872954573f8eaacb67ac2e4fdd10')
    message = client.messages.create(
    body="whats app message is delevered",
    from_='whatsapp:+14155238886',  # Twilio sandbox number
    to='whatsapp:+919538505753'     # Your verified WhatsApp number
    )
    return {
        "Message sent:", message.sid
    }
@app.get("/newsgold")
def newsgold():
    url = "https://www.goodreturns.in/gold-rates/"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")

    # Try to find the table
    table = soup.find("table", {"class": "gold_silver_table"})

    # Check if the table was found
    if table:
        rows = table.find_all("tr")
        body = []

    for row in rows[1:]:
        # Skip header
        cols = row.find_all("td")
        if len(cols) >= 3:
            city = cols[0].text.strip()
            gold_22k = cols[1].text.strip()
            gold_24k = cols[2].text.strip()
            body.append({
                "City": city,
                "22K Gold (₹/10g)": gold_22k,
                "24K Gold (₹/10g)": gold_24k
            })

    return {
        "Message"
    
    }






