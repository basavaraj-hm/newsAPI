
import tempfile
import json
import subprocess
import sys
import textwrap
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import re

app = FastAPI(title="Scrapy + FastAPI (Single File)")

URL_REGEX = re.compile(r"^https?://", re.IGNORECASE)

# Inline Scrapy spider code as a string
SPIDER_CODE = textwrap.dedent("""
import scrapy
from w3lib.html import replace_escape_chars

class TextSpider(scrapy.Spider):
    name = "textspider"

    def __init__(self, url=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not url:
            raise ValueError("url parameter is required")
        self.start_urls = [url]

    def parse(self, response):
        # Extract all visible text nodes under <body>
        texts = response.xpath("//body//text()[normalize-space()]").getall()
        cleaned = [replace_escape_chars(t.strip(), which_escapes=()) for t in texts if t.strip()]
        page_text = " ".join(cleaned)

        title = response.xpath("//title/text()").get() or ""
        yield {
            "url": response.url,
            "title": title.strip(),
            "text": page_text
        }
""")


def run_spider_once(url: str):
    """
    Run the inline Scrapy spider via `scrapy runspider` and return parsed items.
    """
    # Create a temporary file for the spider
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as spider_file:
        spider_path = spider_file.name
        spider_file.write(SPIDER_CODE)

    # Create a temporary file for JSON output
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as out_file:
        out_path = out_file.name

    # Build the command
    cmd = [
        sys.executable, "-m", "scrapy", "runspider", spider_path,
        "-a", f"url={url}",
        "-o", out_path,
        "-t", "json"
    ]

    # Run the spider
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Handle errors
    if result.returncode != 0:
        raise RuntimeError(f"Scrapy failed: {result.stderr.strip() or result.stdout.strip()}")

    # Read the JSON output
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to read spider output: {e}")

    return data


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/scrape")
def scrape(url: str = Query(..., description="Full URL to scrape (http/https)")):
    if not URL_REGEX.match(url):
        raise HTTPException(status_code=400, detail="Invalid URL. Must start with http:// or https://")

    try:
        items = run_spider_once(url)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    return JSONResponse(content={"count": len(items), "items": items})


if __name__ == "__main__":
    # Run FastAPI with uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
