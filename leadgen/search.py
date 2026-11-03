from __future__ import annotations

import time

import httpx

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"

COUNTRIES = [("US", "the United States"), ("CA", "Canada"), ("AU", "Australia"), ("GB", "the United Kingdom")]
TEMPLATES = [
    ("market-expansion", "SaaS startup announces expansion into {c} market"),
    ("product-launch", "e-commerce brand launches in {c} new market entry"),
    ("strategy-hiring", "company hiring market research manager {c}"),
]


def build_queries(max_queries: int) -> list[dict]:
    out = []
    for segment, template in TEMPLATES:
        for code, name in COUNTRIES:
            out.append({"query": template.replace("{c}", name), "country": code, "segment": segment})
    return out[:max_queries]


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
