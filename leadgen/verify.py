"""Turn the model's raw JSON into a verified, scored lead. No model output is trusted blindly:
emails, names, websites and profile URLs must appear verbatim in the scraped source text."""
from __future__ import annotations

from dataclasses import dataclass, field

from .util import FREE_MAIL, NF, TARGET_COUNTRIES, clean, domain_of, now_iso

DRAFT_STATUS = "DRAFT - awaiting your review (never sent automatically)"


@dataclass
class Known:
    """Keys of leads already stored, used for de-duplication."""

    keys: set = field(default_factory=set)
    emails: set = field(default_factory=set)

    @classmethod
    def from_rows(cls, rows: list[dict]) -> "Known":
        k = cls()
        for r in rows:
            k.add(r.get("dedupe_key"), r.get("domain"), r.get("company_name"), r.get("business_email"))
        return k

    def add(self, key=None, domain=None, company=None, email=None) -> None:
        for v in (key, domain):
            if v and v != NF:
                self.keys.add(str(v).lower())
        if company and company != NF:
            self.keys.add("name:" + str(company).lower())
        if email and email != NF:
            self.emails.add(str(email).lower())

    def is_duplicate(self, key: str, name_key: str, email: str) -> bool:
        return bool(
            (key and key in self.keys)
            or (name_key and name_key in self.keys)
            or (email != NF and email in self.emails)
        )


def _num(v, maximum: int) -> int:
    try:
        n = round(float(v))
    except (TypeError, ValueError):
        return 0
    return max(0, min(n, maximum))


def _list(v) -> list[str]:
    return [str(x) for x in v if x] if isinstance(v, list) else []


def verify_and_score(raw: dict, source: dict, page_text: str, page_ok: bool, settings, known: Known,
                     run_id: str, discovered_at: str | None = None) -> dict:
    """Return a lead dict with status in {qualified, rejected, duplicate}."""
    base = {"source_url": source["source_url"], "source_domain": source.get("source_domain", ""),
            "score": 0, "detail": ""}

    if raw.get("is_target_company") is not True:
        base.update(status="rejected",
                    detail=str(raw.get("rejection_reason") or "Not a single identifiable target company")[:300])
        return base

    hay = " ".join([page_text or "", source.get("snippet", ""), source.get("title", ""),
                    source["source_url"]]).lower()
    assumptions, verified = _list(raw.get("assumptions")), _list(raw.get("verified_facts"))
    src_domain = source.get("source_domain", "")

    company = clean(raw.get("company_name"))
    website, domain = clean(raw.get("website")), ""
    if website != NF:
        domain = domain_of(website)
        if not domain or (domain not in hay and domain != src_domain):
            assumptions.append(f"Website {website} was proposed but not found in the source text - discarded")
            website, domain = NF, ""
        elif not website.lower().startswith("http"):
            website = "https://" + domain

    email = clean(raw.get("business_email"))
    if email != NF:
        email = email.lower()
        ed = email.split("@")[1] if "@" in email else ""
        ok = ("@" in email and email in hay and ed not in FREE_MAIL
              and (ed == domain or (domain and ed.endswith("." + domain)) or ed == src_domain))
        if not ok:
            assumptions.append("Email proposed by the model could not be verified in the source text and company domain - discarded")
            email = NF

    contact, title = clean(raw.get("contact_name")), clean(raw.get("contact_title"))
    if contact != NF and contact.lower() not in hay:
        assumptions.append("Contact name not found verbatim in the source text - discarded")
        contact = NF
    if contact == NF:
        title = NF

    linkedin = clean(raw.get("linkedin_url"))
    if linkedin != NF:
        stripped = linkedin.lower().replace("https://", "").replace("http://", "").replace("www.", "")
        if "linkedin.com/" not in stripped or stripped not in hay:
            linkedin = NF

    country, industry, size = clean(raw.get("country")), clean(raw.get("industry")), clean(raw.get("company_size"))
    fit, sig = _num(raw.get("fit_score"), 30), _num(raw.get("signal_score"), 25)
    role = 0 if contact == NF else _num(raw.get("role_score"), 15)
    si = _num(raw.get("size_industry_score"), 15)
    filled = sum(1 for x in (company, website, industry, country, size, contact, email, linkedin) if x != NF)
    quality = round(filled * 10 / 8) + (3 if page_ok else 0) + (2 if domain and domain == src_domain else 0)
    geo_penalty = 15 if (country != NF and country not in TARGET_COUNTRIES) else 0
    score = max(0, min(100, fit + sig + role + si + quality - geo_penalty))

    name_key = f"name:{company.lower()}" if company != NF else ""
    key = domain or name_key
    status, detail = "qualified", ""
    if not key:
        status, detail = "rejected", "Company could not be identified from the source text"
    elif known.is_duplicate(key, name_key, email):
        status, detail = "duplicate", "Already in lead table or earlier in this run"
    elif score < settings.min_score:
        status, detail = "rejected", f"Score {score} is below the threshold of {settings.min_score}"
    if status == "qualified":
        known.add(key, domain, company, email)

    draft, draft_status = "", "Not drafted"
    body = str(raw.get("outreach_body") or "").strip()
    if status == "qualified" and score >= settings.draft_min_score and len(body) > 40:
        draft = (f"Subject: {raw.get('outreach_subject') or 'Quick question'}\n\n{body}\n\n"
                 f"Best regards,\n{settings.sender_name}\n{settings.postal_address}\n\n{settings.opt_out_line}")
        draft_status = DRAFT_STATUS

    base.update(
        status=status, detail=detail, score=score, dedupe_key=key, company_name=company, website=website,
        domain=domain or NF, industry=industry, country=country, company_size=size, contact_name=contact,
        contact_title=title, business_email=email, linkedin_url=linkedin, reason=clean(raw.get("reason_for_fit")),
        discovered_at=discovered_at or now_iso(),
        score_breakdown=(f"fit {fit}/30, signals {sig}/25, role {role}/15, size-industry {si}/15, "
                         f"data-quality {quality}/15" + (", outside priority geography -15" if geo_penalty else "")),
        qualification_notes=str(raw.get("qualification_notes") or "")[:600],
        verified_facts=" | ".join(verified)[:1500], assumptions=" | ".join(assumptions)[:1500],
        outreach_draft=draft, outreach_status=draft_status, run_id=str(run_id),
    )
    return base
