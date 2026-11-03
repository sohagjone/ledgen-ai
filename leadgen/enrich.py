"""Second pass for qualified leads: find the company's own site and keep only business emails
that are published there, on the company's own domain. Never guesses or constructs addresses."""
from __future__ import annotations

from .scrape import Fetcher
from .search import brave_search
from .util import FREE_MAIL, NF, domain_of, is_blocked

ROLE_HINTS = ["partner", "business", "hello", "contact", "info", "enquir", "sales", "marketing", "press", "media", "team", "support"]
_SEPS = ["mailto:", "<", ">", "(", ")", "[", "]", "{", "}", ",", ";", "|", "*", ":", "=", "'", '"', "\n", "\t"]
_BAD_EXT = (".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".css", ".js")


def extract_emails(text: str, domain: str) -> list[str]:
    """Emails literally present in text whose domain is `domain` (or a subdomain). Free-mail excluded."""
    t = str(text or "").lower()
    for sep in _SEPS:
        t = t.replace(sep, " ")
    found: list[str] = []
    for tok in t.split():
        s = tok.strip().rstrip(".")
        parts = s.split("@")
        if len(parts) != 2 or not parts[0] or "." not in parts[1] or len(s) > 80:
            continue
        if s.endswith(_BAD_EXT):
            continue
        ed = parts[1]
        if ed in FREE_MAIL:
            continue
        if (ed == domain or ed.endswith("." + domain)) and s not in found:
            found.append(s)
    return found


def best_email(candidates: list[tuple[str, str]], contact_name: str) -> tuple[str, str] | None:
    """Pick the most useful published email: matches the named contact first, then role mailboxes."""
    toks = [t for t in str(contact_name or "").lower().split() if len(t) > 2]
    best, best_rank = None, 999
    for email, url in candidates:
        local = email.split("@")[0]
        rank = 500
        if any(t in local for t in toks):
            rank = 0
        else:
            for i, hint in enumerate(ROLE_HINTS, start=1):
                if hint in local and i < rank:
                    rank = i
        if rank < best_rank:
            best, best_rank = (email, url), rank
    return best


def enrich_lead(lead: dict, fetcher: Fetcher, client, brave_key: str, stored) -> dict:
    """Mutates and returns `lead`. `stored` = Known built from previously stored leads only.
    Safe to call when nothing is found."""
    if lead.get("status") != "qualified":
        return lead
    if lead["business_email"] != NF and lead["website"] != NF:
        return lead

    dom = lead["domain"] if lead.get("domain") not in (None, NF) else ""
    inferred = not dom
    token = "".join(c for c in lead["company_name"].lower().split(" ")[0] if c.isalnum())
    query = f'"{lead["company_name"]}" official website contact'
    try:
        results = brave_search(client, brave_key, query, count=5, freshness=None)
    except RuntimeError:
        return lead

    pages: list[str] = []
    for r in results:
        d = domain_of(r["url"])
        if not d or is_blocked(d):
            continue
        if not dom and len(token) >= 4 and token in d:
            dom = d
        if dom and d == dom and len(pages) < 2 and r["url"] not in pages:
            pages.append(r["url"])
    if not dom:
        return lead
    if len(pages) < 2 and "https://" + dom not in pages:
        pages.append("https://" + dom)

    candidates: list[tuple[str, str]] = []
    for url in pages:
        page = fetcher.fetch(url)
        if page["ok"]:
            candidates += [(e, url) for e in extract_emails(page["full_text"], dom)]

    if lead["website"] == NF and inferred:
        lead["website"], lead["domain"], lead["dedupe_key"] = "https://" + dom, dom, dom
        lead["assumptions"] = (lead["assumptions"] + " | " if lead["assumptions"] else "") + (
            f"Website {dom} was inferred from a web search match on the company name - please verify")
    pick = best_email(candidates, lead.get("contact_name", ""))
    if pick and lead["business_email"] == NF:
        email, url = pick
        lead["business_email"] = email
        lead["verified_facts"] = (lead["verified_facts"] + " | " if lead["verified_facts"] else "") + (
            f"Email {email} is published on {url}")
        lead["score"] = min(100, int(lead["score"]) + 3)
        lead["score_breakdown"] += ", published email +3"
    # a website/email found only now may match a lead stored in an earlier run
    if ((lead["domain"] != NF and lead["domain"].lower() in stored.keys)
            or (lead["business_email"] != NF and lead["business_email"].lower() in stored.emails)):
        lead["status"] = "duplicate"
        lead["detail"] = "Already in lead table (found after enrichment)"
        lead["outreach_draft"], lead["outreach_status"] = "", "Not drafted"
    return lead
