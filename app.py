
# app.py
import re
import base64
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse

APP_NAME = "URL Fetch (Full Response JSON)"
app = FastAPI(title=APP_NAME)

DEFAULT_TIMEOUT = 20.0
MAX_CONTENT_BYTES = 10 * 1024 * 1024  # 10 MB cap to prevent huge downloads
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
    f"{APP_NAME}"
)
ALLOWED_SCHEMES = {"http", "https"}


def normalize_url(url: str) -> str:
    url = url.strip()
    # Prepend https:// if missing scheme
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
    if not parsed.netloc:
        raise ValueError("URL must include a hostname")
    return url


def is_text_like(content_type: Optional[str]) -> bool:
    if not content_type:
        return False
    ct = content_type.split(";")[0].strip().lower()
    return (
        ct.startswith("text/")
        or ct in {"application/json", "application/xml", "application/xhtml+xml"}
    )


@app.get("/fetch")
async def fetch(
    url: str = Query(..., description="Target URL to fetch"),
    timeout: float = Query(DEFAULT_TIMEOUT, ge=1.0, le=120.0, description="Timeout in seconds"),
    max_bytes: int = Query(MAX_CONTENT_BYTES, ge=1_000, le=100_000_000, description="Max bytes to read"),
    follow_redirects: bool = Query(True, description="Follow HTTP redirects"),
):
    try:
        normalized = normalize_url(url)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }

    try:
        async with httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(timeout),
            follow_redirects=follow_redirects,
            max_redirects=5,
            http2=False,  # set to True only if you install httpx[http2]
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=20),
        ) as client:
            resp = await client.get(normalized)

            # Enforce content-size safety
            content_length_hdr = resp.headers.get("Content-Length")
            if content_length_hdr:
                try:
                    content_length_val = int(content_length_hdr)
                except ValueError:
                    content_length_val = 0
            else:
                content_length_val = 0

            # Read at most max_bytes
            body = resp.content[:max_bytes]
            truncated = content_length_val > max_bytes or len(resp.content) > len(body)

            content_type = resp.headers.get("Content-Type", "")
            result: Dict[str, Any] = {
                "request_url": normalized,
                "final_url": str(resp.url),
                "status": resp.status_code,
                "reason": resp.reason_phrase,
                "http_version": resp.http_version,  # e.g., "HTTP/1.1" or "HTTP/2"
                "headers": dict(resp.headers),
                "content_type": content_type,
                "content_length_header": content_length_val,
                "bytes_returned": len(body),
                "truncated": truncated,
            }

            if is_text_like(content_type):
                # Decode using response encoding (falls back to apparent encoding)
                text = None
                try:
                    text = resp.text if len(body) == len(resp.content) else body.decode(resp.encoding or "utf-8", errors="replace")
                except Exception:
                    text = body.decode("utf-8", errors="replace")

                result["text"] = text
            else:
                # Return base64 for binary/non-text content
                result["content_base64"] = base64.b64encode(body).decode("ascii")

            return JSONResponse(content=result)

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"Timed out fetching {normalized}")
    except httpx.RequestError as re:
        raise HTTPException(status_code=502, detail=f"Request error: {re}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")
