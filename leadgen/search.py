from __future__ import annotations

import time

import httpx

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"

# code -> name used inside the search query
COUNTRIES = {"US": "the United States", "CA": "Canada", "AU": "Australia", "GB": "the United Kingdom"}
COUNTRY_LABELS = {"US": "United States", "CA": "Canada", "AU": "Australia", "GB": "United Kingdom"}

# key -> (label shown in the app, query template). {ind} = "<industry> company" or "company"
SIGNALS = {
    "expansion": ("Market expansion", "{ind} announces expansion into {c} market"),
    "launch": ("Product launch / market entry", "{ind} launches new product in {c} market entry"),
    "hiring": ("Hiring strategy or research roles", "{ind} hiring market research manager {c}"),
    "funding": ("Funding round (growth plans)", "{ind} raises funding to grow in {c}"),
}
DEFAULT_SIGNALS = ["expansion", "launch", "hiring"]


def clean_text(value: str | None, limit: int = 80) -> str:
    """Sanitise free-text user input: printable characters only, no quotes, collapsed spaces, length-capped."""
    if not value:
        return ""
    text = "".join(ch if ch.isprintable() else " " for ch in str(value))
    text = text.replace('"', " ").replace("\\", " ")
    return " ".join(text.split())[:limit]


def describe_focus(industry: str = "", keywords: str = "") -> str:
    parts = []
    if clean_text(industry):
        parts.append(f"industry = {clean_text(industry)}")
    if clean_text(keywords):
        parts.append(f"extra keywords = {clean_text(keywords)}")
    return "; ".join(parts)


def build_queries(max_queries: int, industry: str = "", keywords: str = "",
                  countries: list[str] | None = None, signals: list[str] | None = None) -> list[dict]:
    """Build search queries from the user's criteria. Unknown country/signal keys are ignored;
    empty selections fall back to all countries / default signals."""
    ind_text = clean_text(industry)
    kw = clean_text(keywords)
    ind = f"{ind_text} company" if ind_text else "company"
    codes = [c for c in (countries or []) if c in COUNTRIES] or list(COUNTRIES)
    keys = [s for s in (signals or []) if s in SIGNALS] or DEFAULT_SIGNALS
    out = []
    for key in keys:
        template = SIGNALS[key][1]
        for code in codes:
            q = template.replace("{ind}", ind).replace("{c}", COUNTRIES[code])
            if kw:
                q += " " + kw
            out.append({"query": q, "country": code, "segment": key})
    return out[: max(1, max_queries)]


def brave_search(client: httpx.Client, api_key: str, query: str, country: str | None = None,
                 count: int = 10, freshness: str | None = "pm") -> list[dict]:
    """Return [{url, title, description}] from the Brave Search API. Retries on 429/5xx."""
    params = {"q": query, "count": count, "text_decorations": "false", "safesearch": "moderate"}
    if country:
        params["country"] = country
    if freshness:
        params["freshness"] = freshness
    headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}
    last_err = None
    for attempt in range(3):
        try:
            r = client.get(BRAVE_URL, params=params, headers=headers, timeout=20)
            if r.status_code == 429 or r.status_code >= 500:
                last_err = f"HTTP {r.status_code}"
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            results = (r.json().get("web") or {}).get("results") or []
            return [
                {"url": x.get("url", ""), "title": x.get("title", ""), "description": x.get("description", "")}
                for x in results
            ]
        except httpx.HTTPError as exc:
            last_err = str(exc)
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Brave Search failed: {last_err}")
