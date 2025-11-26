
# app.py
import re
import asyncio
from typing import Optional, List, Dict
from urllib.parse import urlparse, urljoin

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse

APP_NAME = "URL Fetch & Page Analyzer (FastAPI)"
app = FastAPI(title=APP_NAME)

# ---- Configs ----
DEFAULT_TIMEOUT = 15.0
MAX_CONTENT_BYTES = 5 * 1024 * 1024  # 5MB cap (avoid huge downloads)
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
    f"{APP_NAME}"
)

ALLOWED_SCHEMES = {"http", "https"}

# ---- Helpers ----
def normalize_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        # If no scheme, default to https
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
    if not parsed.netloc:
        raise ValueError("URL must include a hostname")
    return url

def extract_text(el) -> Optional[str]:
    if not el:
        return None
    txt = el.get_text(strip=True)
    return txt or None

def safe_meta(soup: BeautifulSoup, name: Optional[str] = None, prop: Optional[str] = None) -> Optional[str]:
    if name:
        m = soup.find("meta", attrs={"name": name})
        if m and m.get("content"):
            return m["content"].strip()
    if prop:
        m = soup.find("meta", attrs={"property": prop})
        if m and m.get("content"):
            return m["content"].strip()
    return None

def extract_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        # Skip javascript/mailto/tel/etc.
        if href.startswith("#") or href.startswith("javascript:") or href.startswith("data:"):
            continue
        abs_url = urljoin(base_url, href)
        # Basic sanity
        try:
            parsed = urlparse(abs_url)
            if parsed.scheme in ALLOWED_SCHEMES and parsed.netloc:
                links.add(abs_url)
        except Exception:
            continue
    return sorted(links)

def content_type_is_html(content_type: Optional[str]) -> bool:
    if not content_type:
        return False
    ct = content_type.split(";")[0].strip().lower()
    return ct in {"text/html", "application/xhtml+xml"}

# ---- Main fetch routine ----
async def fetch_url(url: str, timeout: float = DEFAULT_TIMEOUT) -> Dict:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }

    async with httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(timeout),
        follow_redirects=True,
        max_redirects=5,
        http2=True,
        limits=httpx.Limits(max_keepalive_connections=5, max_connections=20),
    ) as client:
        resp = await client.get(url)
        status = resp.status_code
        final_url = str(resp.url)
        content_type = resp.headers.get("Content-Type", "")
        content_length = int(resp.headers.get("Content-Length", "0") or 0)

        # Guard against huge bodies
        if content_length and content_length > MAX_CONTENT_BYTES:
            raise HTTPException(status_code=413, detail=f"Content too large: {content_length} bytes")

        # Load partial if unknown size
        body_bytes = resp.content[:MAX_CONTENT_BYTES]

        result: Dict = {
            "request_url": url,
            "final_url": final_url,
            "status": status,
            "content_type": content_type,
            "content_length": min(len(body_bytes), content_length or len(body_bytes)),
            "is_html": content_type_is_html(content_type),
            "page": {},
        }

        if not result["is_html"]:
            # For non-HTML: return headers only
            return result

        # Parse HTML
        soup = BeautifulSoup(body_bytes, "lxml")

        # Core page fields
        title_el = soup.find("title")
        canonical_el = soup.find("link", rel=lambda v: v and "canonical" in v)
        description = safe_meta(soup, name="description")
        og_title = safe_meta(soup, prop="og:title")
        og_desc = safe_meta(soup, prop="og:description")
        og_image = safe_meta(soup, prop="og:image")
        twitter_title = safe_meta(soup, name="twitter:title")
        twitter_desc = safe_meta(soup, name="twitter:description")
        twitter_image = safe_meta(soup, name="twitter:image")

        # Headings
        h1 = [extract_text(h) for h in soup.find_all("h1")]
        h2 = [extract_text(h) for h in soup.find_all("h2")]
        h3 = [extract_text(h) for h in soup.find_all("h3")]
        h1 = [t for t in h1 if t]
        h2 = [t for t in h2 if t]
        h3 = [t for t in h3 if t]

        # Links
        links = extract_links(soup, final_url)

        result["page"] = {
            "title": extract_text(title_el),
            "canonical": canonical_el["href"].strip() if canonical_el and canonical_el.get("href") else None,
            "meta": {
                "description": description,
                "og": {
                    "title": og_title,
                    "description": og_desc,
                    "image": og_image,
                },
                "twitter": {
                    "title": twitter_title,
                    "description": twitter_desc,
                    "image": twitter_image,
                },
            },
            "headings": {
                "h1": h1,
                "h2": h2,
                "h3": h3,
            },
            "links": links,
        }

        return result

# ---- FastAPI endpoint ----
@app.get("/search")
async def search_by_url(
    url: str = Query(..., description="Target URL to fetch and analyze"),
    timeout: float = Query(DEFAULT_TIMEOUT, ge=1.0, le=60.0, description="Timeout in seconds"),
):
    try:
        normalized = normalize_url(url)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    try:
        result = await fetch_url(normalized, timeout=timeout)
        return JSONResponse(content=result)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"Timed out fetching {normalized}")
    except httpx.RequestError as re:
        raise HTTPException(status_code=502, detail=f"Request error: {re}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")
