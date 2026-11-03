"""Tests for the Groq call, using httpx's MockTransport (no network)."""
import json

import httpx
import pytest

from leadgen import qualify as q

SRC = {"source_url": "https://x.com/a", "title": "t", "snippet": "s", "query": "q", "country": "US"}


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def ok_response(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_success_sends_json_mode_and_bearer_key():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        seen["url"] = str(request.url)
        return ok_response('{"is_target_company": true, "company_name": "Acme"}')

    out = q.qualify(client_for(handler), "gsk_test", "llama-3.3-70b-versatile", SRC, "page text")
    assert out["company_name"] == "Acme"
    assert seen["auth"] == "Bearer gsk_test"
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["model"] == "llama-3.3-70b-versatile"
    assert seen["body"]["messages"][0]["role"] == "system"
    assert "page text" in seen["body"]["messages"][1]["content"]


def test_rate_limit_is_retried_using_retry_after(monkeypatch):
    sleeps, calls = [], {"n": 0}
    monkeypatch.setattr(q.time, "sleep", lambda s: sleeps.append(s))

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"retry-after": "7"}, json={"error": "rate limit"})
        return ok_response('{"is_target_company": false}')

    assert q.qualify(client_for(handler), "k", "m", SRC, "")["is_target_company"] is False
    assert calls["n"] == 3 and sleeps == [7.0, 7.0]


def test_gives_up_after_repeated_rate_limits(monkeypatch):
    monkeypatch.setattr(q.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="failed after retries"):
        q.qualify(client_for(lambda r: httpx.Response(429, json={})), "k", "m", SRC, "")


def test_bad_key_fails_fast_without_retry(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(q.time, "sleep", lambda s: None)

    def handler(request):
        calls["n"] += 1
        return httpx.Response(401, json={"error": {"message": "Invalid API Key"}})

    with pytest.raises(RuntimeError, match="Groq API error 401"):
        q.qualify(client_for(handler), "bad", "m", SRC, "")
    assert calls["n"] == 1


def test_truncated_or_non_json_output_raises():
    with pytest.raises(RuntimeError, match="not valid JSON"):
        q.qualify(client_for(lambda r: ok_response('{"company_name": "Acme", "outreach_body":')), "k", "m", SRC, "")


def test_json_wrapped_in_text_is_still_parsed():
    out = q.qualify(client_for(lambda r: ok_response('Here you go: {"is_target_company": true} done')), "k", "m", SRC, "")
    assert out["is_target_company"] is True


def test_long_pages_are_truncated_in_prompt():
    prompt = q.build_user_prompt(SRC, "Z" * 50_000)
    assert prompt.count("Z") == q.MAX_CONTENT_CHARS
