from fastapi import FastAPI, Query
from scrape import scrape

app = FastAPI()

@app.get("/scrape")
def scrape_api(url: str = Query(...)):
    data = scrape(url)
    return data  # Returns structured JSON with fields like title, description, links, etc.
