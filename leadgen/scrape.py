from __future__ import annotations

from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura
from bs4 import BeautifulSoup

BOT_NAME = "LeadGenBot"


class Fetcher:
    """Polite page fetcher: honours robots.txt, never tries to get past logins, paywalls or CAPTCHAs."""

    def __init__(self, user_agent: str, timeout: int = 25):
        self.client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Language": "en"},
            timeout=timeout,
            follow_redirects=True,
        )
        self._robots: dict[str, RobotFileParser] = {}

    def close(self) -> None:
        self.client.close()

    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        rp = self._robots.get(origin)
        if rp is None:
            rp = RobotFileParser()
            try:
                r = self.client.get(origin + "/robots.txt", timeout=10)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                elif r.status_code in (401, 403):
                    rp.disallow_all = True
                else:
                    rp.parse([])
            except Exception:
                rp.parse([])
            rp.modified()
            self._robots[origin] = rp
        return rp.can_fetch(BOT_NAME, url)

    def fetch(self, url: str) -> dict:
        """Return {ok, text, full_text, error}. text = main content, full_text = whole page + mailto links."""
        fail = lambda msg: {"ok": False, "text": "", "full_text": "", "error": msg}  # noqa: E731
        if not self.allowed(url):
            return fail("skipped: disallowed by robots.txt")
        try:
            r = self.client.get(url)
        except Exception as exc:  # network errors are expected sometimes
            return fail(f"request failed: {exc}")
        if r.status_code >= 400:
            return fail(f"HTTP {r.status_code}")
        if "html" not in r.headers.get("content-type", "text/html").lower():
            return fail("not an HTML page")
        html = r.text[:1_500_000]
        low = html.lower()
        if ("captcha" in low or "are you a robot" in low) and len(html) < 20_000:
            return fail("skipped: bot-wall / CAPTCHA page")
        main = trafilatura.extract(html, include_comments=False) or ""
        soup = BeautifulSoup(html, "html.parser")
        mailtos = [
            a["href"][7:].split("?")[0]
            for a in soup.find_all("a", href=True)
            if a["href"].lower().startswith("mailto:")
        ]
        full = soup.get_text(" ", strip=True)
        text = main or full[:12_000]
        return {"ok": bool(text), "text": text, "full_text": full + " " + " ".join(mailtos), "error": ""}
