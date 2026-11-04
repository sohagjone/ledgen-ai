"""End-to-end pipeline test with the network pieces faked (no real API calls)."""
import json

from leadgen import pipeline
from leadgen.db import DB
from tests.test_core import settings

ARTICLE = ("AnyMind Group (anymindgroup.com) launches in the US. CEO Kosuke Sogo said the Los Angeles team will "
           "expand. Contact: partnerships@anymindgroup.com")


class FakeFetcher:
    def __init__(self, *a, **k): pass
    def close(self): pass
    def fetch(self, url):
        return {"ok": True, "text": ARTICLE, "full_text": ARTICLE, "error": ""}


def fake_qualify(client, api_key, model, source, content, focus=""):
    return {"is_target_company": True, "company_name": "AnyMind Group", "website": "Not found", "industry": "Adtech",
            "country": "USA", "company_size": "Not found", "contact_name": "Kosuke Sogo", "contact_title": "CEO",
            "business_email": "Not found", "linkedin_url": "Not found", "reason_for_fit": "US launch",
            "verified_facts": ["Launched US operations"], "assumptions": [], "fit_score": 20, "signal_score": 22,
            "role_score": 13, "size_industry_score": 11, "qualification_notes": "", "outreach_subject": "s",
            "outreach_body": "y" * 90}


def fake_search(client, key, query, country=None, count=10, freshness="pm"):
    if "official website" in query:
        return [{"url": "https://anymindgroup.com/contact/", "title": "t", "description": "d"}]
    return [{"url": "https://news.example.com/a", "title": "t", "description": "d"},
            {"url": "https://www.linkedin.com/company/x", "title": "blocked", "description": "d"},
            {"url": "https://news.example.com/a", "title": "dupe url", "description": "d"}]


def patch(monkeypatch):
    monkeypatch.setattr(pipeline, "Fetcher", FakeFetcher)
    monkeypatch.setattr(pipeline, "qualify", fake_qualify)
    monkeypatch.setattr(pipeline, "brave_search", fake_search)
    monkeypatch.setattr("leadgen.enrich.brave_search", fake_search)
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: None)


def test_dry_run_stores_nothing_and_enriches(monkeypatch, tmp_path):
    patch(monkeypatch)
    s = settings(db_path=str(tmp_path / "x.db"))
    res = pipeline.run_pipeline(s, live=False, max_queries=1, max_candidates=5)
    assert len(res.items) == 1                       # linkedin blocked, duplicate URL collapsed
    lead = res.qualified[0]
    assert lead["business_email"] == "partnerships@anymindgroup.com"   # published on the company domain
    assert lead["website"] == "https://anymindgroup.com" and "inferred" in lead["assumptions"]
    assert DB(s.db_path).leads() == []               # dry run: nothing written


def test_live_run_stores_then_second_run_skips(monkeypatch, tmp_path):
    patch(monkeypatch)
    s = settings(db_path=str(tmp_path / "x.db"))
    first = pipeline.run_pipeline(s, live=True, max_queries=1, max_candidates=5)
    assert first.count("qualified") == 1
    assert len(DB(s.db_path).leads()) == 1
    second = pipeline.run_pipeline(s, live=True, max_queries=1, max_candidates=5)
    assert second.items == []                        # already processed: not re-scraped, no duplicate
    pipeline.log_run(s, first, "sent")
    assert DB(s.db_path).runs()[0]["qualified"] == 1


def test_llm_failure_is_reported_not_fatal(monkeypatch, tmp_path):
    patch(monkeypatch)
    def boom(*a, **k): raise RuntimeError("Groq API error 400: bad request")
    monkeypatch.setattr(pipeline, "qualify", boom)
    res = pipeline.run_pipeline(settings(db_path=str(tmp_path / "x.db")), live=False, max_queries=1)
    assert res.items[0]["status"] == "error" and any("400" in e for e in res.errors)


def test_user_criteria_flow_through_pipeline(monkeypatch, tmp_path):
    patch(monkeypatch)
    seen = {"queries": [], "focus": []}
    def spy_search(client, key, query, country=None, count=10, freshness="pm"):
        seen["queries"].append((query, country)); return fake_search(client, key, query, country, count, freshness)
    def spy_qualify(client, api_key, model, source, content, focus=""):
        seen["focus"].append(focus); return fake_qualify(client, api_key, model, source, content, focus)
    monkeypatch.setattr(pipeline, "brave_search", spy_search)
    monkeypatch.setattr(pipeline, "qualify", spy_qualify)
    res = pipeline.run_pipeline(settings(db_path=str(tmp_path / "x.db")), live=False, max_queries=5, max_candidates=3,
                                industry="adtech", keywords="APAC", countries=["AU"], signals=["launch"])
    assert seen["queries"][0] == ("adtech company launches new product in Australia market entry APAC", "AU")
    assert seen["focus"] == ["industry = adtech; extra keywords = APAC"]
    assert res.criteria["industry"] == "adtech"
