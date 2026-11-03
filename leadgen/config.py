from __future__ import annotations

import os
from dataclasses import dataclass


def _get(name: str, default: str = "") -> str:
    """Read from environment first, then Streamlit secrets (when running in Streamlit)."""
    val = os.environ.get(name)
    if val:
        return val
    try:
        import streamlit as st  # noqa: WPS433

        return str(st.secrets.get(name, default))
    except Exception:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(_get(name, str(default)))
    except ValueError:
        return default


@dataclass
class Settings:
    groq_api_key: str
    brave_api_key: str
    model: str
    smtp_user: str
    smtp_password: str
    notify_email: str
    sender_name: str
    postal_address: str
    opt_out_line: str
    min_score: int
    draft_min_score: int
    max_queries: int
    max_candidates: int
    max_enrich: int
    db_path: str
    user_agent: str

    def missing_for_run(self) -> list[str]:
        out = []
        if not self.groq_api_key:
            out.append("GROQ_API_KEY")
        if not self.brave_api_key:
            out.append("BRAVE_API_KEY")
        return out


def load_settings() -> Settings:
    return Settings(
        groq_api_key=_get("GROQ_API_KEY"),
        brave_api_key=_get("BRAVE_API_KEY"),
        model=_get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        smtp_user=_get("SMTP_USER"),
        smtp_password=_get("SMTP_PASSWORD"),
        notify_email=_get("NOTIFY_EMAIL", "sohagjone@gmail.com"),
        sender_name=_get("SENDER_NAME", "EDIT ME: your name and business"),
        postal_address=_get("POSTAL_ADDRESS", "EDIT ME: your postal address"),
        opt_out_line=_get(
            "OPT_OUT_LINE",
            'If you would rather not hear from me, just reply "no thanks" and I will not contact you again.',
        ),
        min_score=_int("MIN_SCORE", 50),
        draft_min_score=_int("DRAFT_MIN_SCORE", 65),
        max_queries=_int("MAX_QUERIES", 12),
        max_candidates=_int("MAX_CANDIDATES", 25),
        max_enrich=_int("MAX_ENRICH", 10),
        db_path=_get("DB_PATH", "data/leads.db"),
        user_agent=_get("USER_AGENT", "LeadGenBot/1.0 (+market research; respects robots.txt)"),
    )
