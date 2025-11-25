
from fastapi import FastAPI
from scrape import Scraper

app = FastAPI()

@app.get("/scrape")
def scrape_page(url: str):
    """
    Scrape the given URL using the scrape module and return the page title and links.
    """
    try:
        scraper = Scraper(url)
        title = scraper.title()  # Get page title
        links = scraper.links()  # Get all links on the page

        return {
            "url": url,
            "title": title,
            "links": links
        }
    except Exception as e:
        return {"error": str(e)}
