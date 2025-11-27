
import os
import re
from typing import Optional, Dict, Any

import requests
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="Gold Rate Fetcher via Google Custom Search API")

API_KEY = os.getenv("AIzaSyCJIlT9KZYlNM2bzBp-ll8oX0CipDmt4dk")      # set this in your environment
CSE_ID  = os.getenv("AIzaSyCJIlT9KZYlNM2bzBp-ll8oX0CipDmt4dk")       # set this in your environment

# --- Regex helpers to pull a price and unit from Google's snippet ---
PRICE_REGEX = re.compile(
    r"""
    (?P<currency>₹|INR|Rs\.?|rupee|USD|\$)\s*                 # currency
    (?P<amount>[0-9]{1,3}(?:[, ]?[0-9]{3})*(?:\.[0-9]+)?)     # amount with commas/decimals
    (?:\s*/\s*(?P<unit>gram|gm|g|10g|10\s*g))?                # optional unit
    """,
    re.IGNORECASE | re.VERBOSE,
)
KARAT_REGEX = re.compile(r"(22k|24k|22kt|24kt|22\s*karat|24\s*karat)", re.IGNORECASE)


def extract_price_from_snippet(snippet: str) -> Dict[str, Any]:
    """Parse a snippet for price, currency, unit, karat (best-effort)."""
    result = {
        "price_text": None,
        "currency": None,
        "amount": None,
        "unit": None,
        "karat": None,
    }
    if not snippet:
        return result

    m = PRICE_REGEX.search(snippet)
    if m:
        result["price_text"] = m.group(0)
        result["currency"] = m.group("currency")
        result["amount"] = (m.group("amount") or "").replace(" ", "")
        unit = (m.group("unit") or "").lower().replace(" ", "")
        if unit:
            if unit in ["g", "gm"]:
                unit = "gram"
            result["unit"] = unit

    k = KARAT_REGEX.search(snippet)
    if k:
        val = k.group(0).lower()
        if "22" in val:
            result["karat"] = "22K"
        elif "24" in val:
            result["karat"] = "24K"

    return result


def google_gold_rate(query="gold rate today in Bengaluru") -> Dict[str, Any]:
    """Fetch top snippet from Google Custom Search API for the query."""
    if not API_KEY or not CSE_ID:
        raise ValueError("Please set GOOGLE_API_KEY and GOOGLE_CSE_ID environment variables.")

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": API_KEY,
        "cx": CSE_ID,
        "q": query,
        "num": 1,
        "hl": "en",
        "gl": "in",  # bias to India results
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()

    items = data.get("items", [])
    if not items:
        return {"query": query, "result": None, "note": "No results from API."}

    top = items[0]
    return {
        "query": query,
        "title": top.get("title"),
        "snippet": top.get("snippet"),
        "link": top.get("link"),
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/gold")
def gold_rate(
    city: str = Query("Bengaluru", description="City to include in the query"),
    karat: Optional[str] = Query(None, description="Optional karat like '22K' or '24K'"),
):
    """
    Returns gold rate information derived from Google's top search result snippet.
    Requires GOOGLE_API_KEY and GOOGLE_CSE_ID to be set.
    """
    query_parts = ["gold rate today", city]
    if karat:
        query_parts.append(karat)
    query = " ".join(query_parts)

    try:
        result = google_gold_rate(query)
    except ValueError as e:
        # Missing env vars
        raise HTTPException(status_code=400, detail=str(e))
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Google API HTTP error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    snippet = result.get("snippet") or ""
    parsed = extract_price_from_snippet(snippet)

    # Friendly hint if price was not parsed
    if not parsed.get("price_text"):
        parsed["note"] = (
            "Could not confidently extract a price from the snippet. "
            "Result formats vary—consider visiting 'source' to parse the actual page."
        )

    payload = {
        "query": result.get("query"),
        "title": result.get("title"),
        "snippet": snippet,
        "source": result.get("link"),
        **parsed,
    }
    return JSONResponse(content=payload)


if __name__ == "__main__":
    # Start FastAPI server
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
