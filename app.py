import httpx
from fastapi import FastAPI, Query

app = FastAPI()

@app.get("/scrape")
async def scrape(url: str = Query(..., description="URL to scrape")):
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return {"content": response.text}
