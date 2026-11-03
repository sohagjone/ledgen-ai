from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

import anthropic
import httpx

from .db import DB
from .enrich import enrich_lead
from .qualify import qualify
from .scrape import Fetcher
from .search import brave_search, build_queries
from .util import NF, domain_of, is_blocked, now_iso
from .verify import Known, verify_and_score


@dataclass
class RunResult:
    run_id: str
    started_at: str
    live: bool
    queries: int = 0
    raw_results: int = 0
    items: list[dict] = field(default_factory=list)   # every analysed candidate with its status
    errors: list[str] = field(default_factory=list)
    existing_rows: list[dict] = field(default_factory=list)  # leads stored before this run

    @property
    def qualified(self) -> list[dict]:
        return sorted([i for i in self.items if i["status"] == "qualified"], key=lambda x: -x["score"])

    def count(self, status: str) -> int:
        return sum(1 for i in self.items if i["status"] == status)


def run_pipeline(settings, live: bool = False, max_queries: int | None = None,
                 max_candidates: int | None = None, log: Callable[[str], None] = lambda m: None) -> RunResult:
    """Discover -> normalise -> scrape -> qualify -> verify/score -> enrich -> (store if live).
    With live=False nothing is written to the database."""
    missing = settings.missing_for_run()
    if missing:
        raise RuntimeError("Missing required settings: " + ", ".join(missing))

    db = DB(settings.db_path)
    result = RunResult(run_id=uuid.uuid4().hex[:8], started_at=now_iso(), live=live)
    result.existing_rows = db.leads()
    stored = Known.from_rows(result.existing_rows)
    known = Known.from_rows(result.existing_rows)
    known_urls = db.processed_urls() | {r["source_url"].lower() for r in result.existing_rows if r.get("source_url")}
    known_domains = {r["domain"].lower() for r in result.existing_rows if r.get("domain") and r["domain"] != NF}

    http = httpx.Client(timeout=30)
    fetcher = Fetcher(settings.user_agent)
    claude = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=3)
    try:
        # 1. Discover
        queries = build_queries(max_queries or settings.max_queries)
        result.queries = len(queries)
        candidates: list[dict] = []
        seen: set[str] = set()
        for q in queries:
            log(f"Searching: {q['query']} [{q['country']}]")
            try:
                found = brave_search(http, settings.brave_api_key, q["query"], q["country"])
            except RuntimeError as exc:
                result.errors.append(f"Brave Search ({q['query']}): {exc}")
                continue
            result.raw_results += len(found)
            for r in found:  # 2. Normalise + pre-dedupe
                url = r["url"].split("#")[0]
                d = domain_of(url)
                if not url or not d or is_blocked(d) or url.lower() in seen or url.lower() in known_urls or d in known_domains:
                    continue
                seen.add(url.lower())
                candidates.append({"source_url": url, "source_domain": d, "title": r["title"],
                                   "snippet": r["description"], "query": q["query"], "country": q["country"]})
            time.sleep(1.0)  # stay under Brave's 1 request/second free-tier limit
        candidates = candidates[: (max_candidates or settings.max_candidates)]
        log(f"{len(candidates)} new candidate pages to analyse")

        # 3-5. Scrape -> qualify -> verify & score
        for i, src in enumerate(candidates, start=1):
            log(f"[{i}/{len(candidates)}] {src['source_url']}")
            page = fetcher.fetch(src["source_url"])
            if not page["ok"]:
                result.errors.append(f"Fetch {src['source_url']}: {page['error']}")
            try:
                raw = qualify(claude, settings.model, src, page["text"])
            except RuntimeError as exc:
                result.errors.append(f"{src['source_url']}: {exc}")
                result.items.append({**src, "status": "error", "detail": str(exc), "score": 0})
                continue
            item = verify_and_score(raw, src, page["text"], page["ok"], settings, known, result.run_id, result.started_at)
            result.items.append(item)
            time.sleep(1.0)

        # 6. Enrich qualified leads (published business emails only)
        for lead in result.qualified[: settings.max_enrich]:
            if lead["business_email"] == NF or lead["website"] == NF:
                log(f"Looking for published email: {lead['company_name']}")
                enrich_lead(lead, fetcher, http, settings.brave_api_key, stored)

        # 7. Store (live only)
        if live:
            for item in result.items:
                if item["status"] == "qualified" and not db.insert_lead(item):
                    item["status"], item["detail"] = "duplicate", "Already stored"
                if item["status"] != "error":
                    db.mark_processed(item, result.run_id, result.started_at)
        return result
    finally:
        http.close()
        fetcher.close()
        db.close()


def log_run(settings, result: RunResult, email_status: str) -> None:
    """Write a run-log row (live runs only)."""
    if not result.live:
        return
    db = DB(settings.db_path)
    db.log_run({
        "run_id": result.run_id, "started_at": result.started_at, "mode": "live", "queries": result.queries,
        "candidates": len(result.items), "qualified": result.count("qualified"),
        "duplicates": result.count("duplicate"), "rejected": result.count("rejected"),
        "error_count": len(result.errors), "error_details": " || ".join(result.errors[:10])[:1500],
        "email_status": email_status,
    })
    db.close()
