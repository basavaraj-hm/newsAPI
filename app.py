
import re
from typing import Optional, Dict, Any

import requests
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="Gold Rate via Google Custom Search API (inline keys)")

# -------------------------------------------------------------------
# Option 1: Hardcode your credentials here (simple but insecure)
GOOGLE_API_KEY = "AIzaSyCJIlT9KZYlNM2bzBp-ll8oX0CipDmt4dk"
GOOGLE_CSE_ID  = "AIzaSyCJIlT9KZYlNM2bzBp-ll8oX0CipDmt4dk"
# -------------------------------------------------------------------

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
    result = {"price_text": None, "currency": None, "amount": None, "unit": None, "karat": None}
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


def google_gold_rate(query: str, api_key: str, cse_id: str) -> Dict[str, Any]:
    """Fetch top result via Google Custom Search API."""
    if not api_key or not cse_id:
        raise ValueError("Missing API key or CSE ID.")

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cse_id,
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
    # Option 2: allow passing key/id via query (overrides hardcoded)
    api_key: Optional[str] = Query(None, description="Google API key (overrides inline)"),
    cse_id: Optional[str] = Query(None, description="Google CSE ID (overrides inline)"),
):
    """
    Returns gold rate info derived from Google's top search result snippet.

    You can:
    - Hardcode GOOGLE_API_KEY and GOOGLE_CSE_ID at the top of the file, OR
    - Pass them as query params: /gold?...&api_key=YOUR_KEY&cse_id=YOUR_CX
    """
    query_parts = ["gold rate today", city]
    if karat:
        query_parts.append(karat)
    query = " ".join(query_parts)

    key = api_key or GOOGLE_API_KEY
    cx  = cse_id or GOOGLE_CSE_ID

    try:
        result = google_gold_rate(query, key, cx)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Google API HTTP error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    snippet = result.get("snippet") or ""
    parsed = extract_price_from_snippet(snippet)

    if not parsed.get("price_text"):
        parsed["note"] = (
            "Could not confidently extract a price from the snippet. "
            "Visit 'source' to parse the actual page for exact values/units."
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
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
