
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

app = FastAPI(title="Scrapy + FastAPI (Single File, Diagnostics)")

URL_REGEX = re.compile(r"^https?://", re.IGNORECASE)

# Inline Scrapy spider with stronger extraction + debug metadata
SPIDER_CODE = textwrap.dedent("""
import scrapy
from w3lib.html import replace_escape_chars

class TextSpider(scrapy.Spider):
    name = "textspider"
    custom_settings = {
        "FEED_EXPORT_ENCODING": "utf-8",
        "DOWNLOAD_TIMEOUT": 30,
        "LOG_LEVEL": "ERROR",
        # Default UA (can be overridden via -s from CLI)
        "USER_AGENT": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "REDIRECT_ENABLED": True,
        "HTTPERROR_ALLOW_ALL": True,  # allow non-2xx statuses to reach parse
    }

    def __init__(self, url=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not url:
            raise ValueError("url parameter is required")
        self.start_urls = [url]

    def parse(self, response):
        # Collect debug info
        title = (response.xpath("//title/text()").get() or "").strip()

        # Robust visible-text extraction (ignore script/style/noscript)
        texts = response.xpath(
            "//body//*[not(self::script or self::style or self::noscript)]/text()[normalize-space()]"
        ).getall()

        cleaned = [replace_escape_chars(t.strip(), which_escapes=()) for t in texts if t.strip()]
        page_text = " ".join(cleaned)

        # Small HTML preview for diagnostics
        preview = response.text[:800] if isinstance(response.text, str) else ""

        yield {
            "url": response.url,
            "status": response.status,
            "title": title,
            "text": page_text,
            "text_len": len(page_text),
            "preview_html": preview,
            "final_url": response.url,  # after redirects
        }
""")

def run_spider_once(url: str, obey_robots: bool, user_agent: str):
    """
    Run the inline Scrapy spider and return JSON feed items.
    """
    # Write the temporary spider file
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as spider_file:
        spider_path = spider_file.name
        spider_file.write(SPIDER_CODE)

    # Ensure Scrapy can write to feed file
    out_fd, out_path = tempfile.mkstemp(suffix=".json")
    os.close(out_fd)

    cmd = [
        sys.executable, "-m", "scrapy", "runspider", spider_path,
        "-a", f"url={url}",
        "-o", out_path,
        "-s", "FEED_FORMAT=json",
        "-s", f"ROBOTSTXT_OBEY={'True' if obey_robots else 'False'}",
        "-s", f"USER_AGENT={user_agent}",
        "-s", "LOG_LEVEL=ERROR",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if result.returncode != 0:
        err_tail = (result.stderr or "")[-2000:]
        out_tail = (result.stdout or "")[-2000:]
        # Clean up temp files
        try: os.remove(spider_path)
        except: pass
        try: os.remove(out_path)
        except: pass
        raise RuntimeError(f"Scrapy exited with code {result.returncode}.\nSTDERR:\n{err_tail}\nSTDOUT:\n{out_tail}")

    try:
        with open(out_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        err_tail = (result.stderr or "")[-2000:]
        out_tail = (result.stdout or "")[-2000:]
        raise RuntimeError(f"Failed to read spider output: {e}\nSTDERR:\n{err_tail}\nSTDOUT:\n{out_tail}")
    finally:
        try: os.remove(spider_path)
        except: pass
        try: os.remove(out_path)
        except: pass

    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected feed format: {type(data)}")

    return data

def fallback_extract(url: str, user_agent: str):
    """
    Lightweight fallback using httpx + parsel without Scrapy.
    """
    import httpx
    from parsel import Selector
    headers = {"User-Agent": user_agent}
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        r = client.get(url, headers=headers)
        r.raise_for_status()
        sel = Selector(r.text)
        title = (sel.xpath("//title/text()").get() or "").strip()
        texts = sel.xpath(
            "//body//*[not(self::script or self::style or self::noscript)]/text()[normalize-space()]"
        ).getall()
        cleaned = [t.strip() for t in texts if t.strip()]
        page_text = " ".join(cleaned)
        preview = r.text[:800]
        return [{
            "url": url,
            "status": r.status_code,
            "title": title,
            "text": page_text,
            "text_len": len(page_text),
            "preview_html": preview,
            "final_url": str(r.url),
        }]

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/scrape")
def scrape(
    url: str = Query(..., description="Full URL to scrape (http/https)"),
    obey_robots: bool = Query(True, description="Obey robots.txt (True/False)"),
    ua: str = Query("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    description="Custom User-Agent string"),
    use_fallback: bool = Query(True, description="Use httpx+parsel fallback if Scrapy fails"),
):
    if not URL_REGEX.match(url):
        raise HTTPException(status_code=400, detail="Invalid URL. Must start with http:// or https://")

    try:
        items = run_spider_once(url, obey_robots=obey_robots, user_agent=ua)
        resp = {"count": len(items), "items": items}
        # If extraction returned empty text, include a hint
        if len(items) == 1 and items[0].get("text_len", 0) == 0:
            resp["hint"] = (
                "No visible text extracted. The page may be JS-rendered, behind consent/login, "
                "or selectors need adjustment. See 'status' and 'preview_html' for clues."
            )
        return JSONResponse(content=resp)
    except RuntimeError as e:
        if use_fallback:
            try:
                fb_items = fallback_extract(url, user_agent=ua)
                return JSONResponse(content={
                    "count": len(fb_items),
                    "items": fb_items,
                    "note": "Returned via fallback extractor because Scrapy failed",
                    "error": str(e)
                })
            except Exception as e2:
                raise HTTPException(status_code=500, detail=f"Scrapy failed and fallback failed.\n{e}\n{e2}")
        else:
            raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

