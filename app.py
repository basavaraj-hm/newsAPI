import requests
from fastapi import FastAPI
import yfinance as yf
from twilio.rest import Client
from bs4 import BeautifulSoup
from nsepython import *
from apscheduler.schedulers.background import BackgroundScheduler
import time



app = FastAPI()


def fetch_price():
    try:
        symbol="NIITLTD"
        data = nse_eq(symbol)
        last_price = data.get("priceInfo", {}).get("lastPrice", None)
        if last_price is not None:
            print(f"Last price of {symbol}: ₹{last_price}")
        else:
            print(f"'lastPrice' not found in priceInfo for {symbol}. Full priceInfo: {data.get('priceInfo')}")
        client = Client('AC81d4b9b02bcc2deb5580f9b988c17c04', '31a95eaf36ddbdcd8de51c32b94aca79')
        message = client.messages.create(
        body=f"Last price of {symbol}: ₹{last_price}",
        from_='whatsapp:+14155238886',  # Twilio sandbox number
        to='whatsapp:+919538505753'     # Your verified WhatsApp number
    )
       
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
    symbol = "RELIANCE"
    last_price = 2523.75  # Replace with actual logic
    print(f"Last price of {symbol}: ₹{last_price} at {time.strftime('%H:%M:%S')}")

# Set up scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(fetch_price, 'interval', seconds=3600)
scheduler.start()


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
    
    client = Client('AC81d4b9b02bcc2deb5580f9b988c17c04', '31a95eaf36ddbdcd8de51c32b94aca79')
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
    try:
        
        
        '''
        url = "https://www.google.com/search?q=gold+rate+today&sca_esv=18be89dfcaae8ca6&sxsrf=AE3TifOhXFnb47OyKpMa10UNi5A-c7XliA%3A1754996211492&source=hp&ei=8x2baPvNG96XnesPkoiHUQ&iflsig=AOw8s4IAAAAAaJssA4s45mCRR9W4ph94b7CigWv_pIux&oq=gold+&gs_lp=Egdnd3Mtd2l6IgVnb2xkICoCCAAyChAjGIAEGCcYigUyChAjGIAEGCcYigUyDRAAGIAEGLEDGEMYigUyDRAAGIAEGLEDGEMYigUyDRAAGIAEGLEDGEMYigUyDRAAGIAEGLEDGEMYigUyDRAAGIAEGLEDGEMYigUyChAAGIAEGEMYigUyCxAAGIAEGJECGIoFMgUQABiABEikG1CbBFjCCXABeACQAQCYAZIBoAGSBaoBAzAuNbgBAcgBAPgBAZgCBqACzAWoAgrCAgcQIxgnGOoCwgILEAAYgAQYsQMYgwHCAhEQABiABBiRAhixAxiDARiKBcICEBAAGIAEGLEDGEMYgwEYigWYAxDxBc4SPqTfLGHekgcDMS41oAf9KbIHAzAuNbgHvAXCBwUyLTQuMsgHLw&sclient=gws-wiz"  
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
        print("Connection successful!")
        print("Status Code:", response.status_code)
        
        soup = BeautifulSoup(response.content, "html.parser")
        print(soup.title.string if soup.title else "No title found")
        print(soup.body.string if soup.body else "No body found")
        print(soup.header.string if soup.heaader else "No header found")
        print(soup.find("in Bengaluru is"))
        '''
        
        
        url = 'https://www.google.com/search?q=gold+rate&sca_esv=5ae40a1c31d56792&sxsrf=AE3TifO1Uomi8dgSG_mz8HjtedIBMADYvQ%3A1755506351353&source=hp&ei=r-aiaOeFE_Xe2roPm-Oy-Qw&iflsig=AOw8s4IAAAAAaKL0vwQcYjsLrmOhH6lohnT7irRSLA_g&ved=0ahUKEwinmeLj-pOPAxV1r1YBHZuxLM8Q4dUDCBo&uact=5&oq=gold+rate&gs_lp=Egdnd3Mtd2l6Iglnb2xkIHJhdGUyChAjGIAEGCcYigUyChAjGIAEGCcYigUyCxAAGIAEGJECGIoFMgsQABiABBiRAhiKBTIIEAAYgAQYsQMyBRAAGIAEMggQABiABBixAzIFEAAYgAQyCBAAGIAEGLEDMgUQABiABEj8KVDtEFiuHXABeACQAQCYAagBoAGVCKoBAzMuNrgBA8gBAPgBAZgCCqACzgioAgrCAgcQIxgnGOoCwgILEAAYgAQYsQMYgwHCAhEQLhiABBixAxjRAxiDARjHAcICDhAAGIAEGJECGLEDGIoFwgIIEC4YgAQYsQPCAg4QLhiABBixAxjRAxjHAZgDCfEFkr1_CVQ5dd-SBwMyLjigB8pNsgcDMS44uAfFCMIHBTAuMS45yAcl&sclient=gws-wiz'

        # Send a GET request to the webpage
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        print("Status Code:", response.status_code)

        # Parse the HTML content using BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Example: Extract all paragraph texts
        paragraphs = soup.find_all('span')
        for span in paragraphs:
            print(span.text)
        
        # Print the text of each span
        for i, span in enumerate(paragraphs, start=1):
            print(f"Span {i} text:", span.text)


    except requests.exceptions.RequestException as e:
        
        print("Connection failed:", e)
       
@app.get("/nseprice/{symbol}")
def nseprice(symbol: str):
    #symbol = "RELIANCE"
    '''
    try:
        data = nse_eq(symbol)
        if 'lastPrice' in data:
            print(f"Last price of {symbol}: {data['lastPrice']}")
        else:
            print(f"'lastPrice' not found in response for {symbol}. Full response: {data}")
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
    '''
    
    try:
        data = nse_eq(symbol)
        last_price = data.get("priceInfo", {}).get("lastPrice", None)
        if last_price is not None:
            print(f"Last price of {symbol}: ₹{last_price}")
        else:
            print(f"'lastPrice' not found in priceInfo for {symbol}. Full priceInfo: {data.get('priceInfo')}")
        client = Client('AC81d4b9b02bcc2deb5580f9b988c17c04', '31a95eaf36ddbdcd8de51c32b94aca79')
        message = client.messages.create(
        body=f"Last price of {symbol}: ₹{last_price}",
        from_='whatsapp:+14155238886',  # Twilio sandbox number
        to='whatsapp:+919538505753'     # Your verified WhatsApp number
    )
        return {
            symbol: data
        }
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")


    


    



















































