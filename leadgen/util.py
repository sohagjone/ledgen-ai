from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

NF = "Not found"

BLOCKED_DOMAINS = (
    "linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "reddit.com", "quora.com", "wikipedia.org", "glassdoor.com",
    "indeed.com", "pinterest.com", "tiktok.com", "crunchbase.com", "zoominfo.com",
)
FREE_MAIL = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "aol.com", "proton.me", "protonmail.com",
}
TARGET_COUNTRIES = {"USA", "Canada", "Australia", "United Kingdom"}


def domain_of(url: str) -> str:
    u = str(url or "").strip()
    if not u:
        return ""
    if "//" not in u:
        u = "//" + u
    host = (urlparse(u).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def is_blocked(domain: str) -> bool:
    return any(domain == b or domain.endswith("." + b) for b in BLOCKED_DOMAINS)


def clean(value) -> str:
    """Normalise empty / placeholder values to 'Not found'."""
    if value is None:
        return NF
    s = str(value).strip()
    if s.lower() in {"", "unknown", "n/a", "null", "none", "not found"}:
        return NF
    return s


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
