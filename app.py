
import tempfile
import json
import subprocess
import sys
import textwrap
import os
import re
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="Scrapy + FastAPI (Single File, Robust)")

URL_REGEX = re.compile(r"^https?://", re.IGNORECASE)

# Inline Scrapy spider code
SPIDER_CODE = textwrap.dedent("""
import scrapy
from w3lib.html import replace_escape_chars

class TextSpider(scrapy.Spider):
    name = "textspider"
    custom_settings = {
        # Be explicit: JSON feed format
        "FEED_EXPORT_ENCODING": "utf-8",
        "ROBOTSTXT_OBEY": True,  # set False if site allows scraping but robots disallow
        "DOWNLOAD_TIMEOUT": 30,
        "USER_AGENT": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # Reduce noise from middleware
        "LOG_LEVEL": "ERROR",
    }

    def __init__(self, url=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not url:
            raise ValueError("url parameter is required")
        self.start_urls = [url]

    def parse(self, response):
        # Extract visible text nodes under <body>
        texts = response.xpath("//body//text()[normalize-space()]").getall()
        cleaned = [replace_escape_chars(t.strip(), which_escapes=()) for t in texts if t.strip()]
        page_text = " ".join(cleaned)

        title = response.xpath("//title/text()").get() or ""

        # Yield a single item
        yield {
            "url": response.url,
            "status": response.status,
            "title": title.strip(),
            "text": page_text
        }
""")

def run_spider_once(url: str):
    """
    Run the inline Scrapy spider via subprocess and return parsed items.
    """
    # Create a temporary spider file
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as spider_file:
        spider_path = spider_file.name
        spider_file.write(SPIDER_CODE)

    # Ensure file is closed before subprocess
    # Create output temp path (closed for Scrapy to write)
    out_fd, out_path = tempfile.mkstemp(suffix=".json")
    os.close(out_fd)  # close the descriptor

    # Build command
    cmd = [
        sys.executable, "-m", "scrapy", "runspider", spider_path,
        "-a", f"url={url}",
        "-o", out_path,
        "-s", "FEED_FORMAT=json",
        "-s", "LOG_LEVEL=ERROR",
        "-s", "USER_AGENT=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # You can disable robots if you are allowed to scrape but robots disallow:
        # "-s", "ROBOTSTXT_OBEY=False",
    ]

    # Run with timeout and capture logs
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    # If non-zero, include stderr/stdout tails for diagnosis
    if result.returncode != 0:
        err_tail = (result.stderr or "")[-2000:]
        out_tail = (result.stdout or "")[-2000:]
        raise RuntimeError(f"Scrapy exited with code {result.returncode}.\nSTDERR:\n{err_tail}\nSTDOUT:\n{out_tail}")

    # Read the JSON output
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        # If empty or invalid JSON, surface logs for context
        err_tail = (result.stderr or "")[-2000:]
        out_tail = (result.stdout or "")[-2000:]
        raise RuntimeError(f"Failed to read spider output: {e}\nSTDERR:\n{err_tail}\nSTDOUT:\n{out_tail}")
    finally:
        # Cleanup temp files
        try:
            os.remove(spider_path)
        except Exception:
            pass
        try:
            os.remove(out_path)
        except Exception:
            pass

    # Ensure we got at least one item
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected feed format: {type(data)}")

    return data


# Optional: lightweight fallback using httpx + parsel when Scrapy fails
def fallback_extract(url: str):
    try:
        import httpx
        from parsel import Selector
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        with httpx.Client(timeout=30) as client:
            r = client.get(url, headers=headers)
            r.raise_for_status()
            sel = Selector(r.text)
            texts = sel.xpath("//body//text()[normalize-space()]").getall()
            cleaned = [t.strip() for t in texts if t.strip()]
            page_text = " ".join(cleaned)
            title = sel.xpath("//title/text()").get() or ""
            return [{"url": url, "status": r.status_code, "title": title.strip(), "text": page_text}]
    except Exception as e:
        raise RuntimeError(f"Fallback extractor failed: {e}")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/scrape")
def scrape(url: str = Query(..., description="Full URL to scrape (http/https)")):
    if not URL_REGEX.match(url):
        raise HTTPException(status_code=400, detail="Invalid URL. Must start with http:// or https://")

    try:
        items = run_spider_once(url)
        return JSONResponse(content={"count": len(items), "items": items})
    except RuntimeError as e:
        # Try fallback extractor if Scrapy failed
        try:
            fallback_items = fallback_extract(url)
            return JSONResponse(content={
                "count": len(fallback_items),
                "items": fallback_items,
                "note": "Returned via fallback extractor because Scrapy failed",
                "error": str(e)
            })
        except Exception as e2:
            raise HTTPException(status_code=500, detail=f"Scrapy failed and fallback failed.\n{e}\n{e2}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)

