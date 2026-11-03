from __future__ import annotations

import sqlite3
from pathlib import Path

LEAD_COLS = [
    "dedupe_key", "company_name", "website", "domain", "industry", "country", "company_size",
    "contact_name", "contact_title", "business_email", "linkedin_url", "reason", "source_url",
    "discovered_at", "score", "score_breakdown", "qualification_notes", "verified_facts",
    "assumptions", "outreach_draft", "outreach_status", "run_id",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dedupe_key TEXT UNIQUE, company_name TEXT, website TEXT, domain TEXT, industry TEXT, country TEXT,
  company_size TEXT, contact_name TEXT, contact_title TEXT, business_email TEXT, linkedin_url TEXT,
  reason TEXT, source_url TEXT, discovered_at TEXT, score INTEGER, score_breakdown TEXT,
  qualification_notes TEXT, verified_facts TEXT, assumptions TEXT, outreach_draft TEXT,
  outreach_status TEXT, run_id TEXT
);
CREATE TABLE IF NOT EXISTS processed (
  source_url TEXT PRIMARY KEY, domain TEXT, outcome TEXT, score INTEGER, reason TEXT, run_id TEXT, processed_at TEXT
);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, started_at TEXT, mode TEXT, queries INTEGER, candidates INTEGER,
  qualified INTEGER, duplicates INTEGER, rejected INTEGER, error_count INTEGER, error_details TEXT, email_status TEXT
);
"""


class DB:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def leads(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM leads ORDER BY discovered_at DESC, id DESC").fetchall()
        return [dict(r) for r in rows]

    def processed_urls(self) -> set[str]:
        return {r["source_url"].lower() for r in self.conn.execute("SELECT source_url FROM processed")}

    def insert_lead(self, lead: dict) -> bool:
        """Insert a lead. Returns False (and does nothing) if its dedupe_key already exists."""
        cols = ", ".join(LEAD_COLS)
        marks = ", ".join("?" for _ in LEAD_COLS)
        try:
            self.conn.execute(f"INSERT INTO leads ({cols}) VALUES ({marks})", [lead.get(c, "") for c in LEAD_COLS])
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def mark_processed(self, item: dict, run_id: str, when: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO processed VALUES (?,?,?,?,?,?,?)",
            (item["source_url"], item.get("source_domain", ""), item["status"], int(item.get("score", 0)),
             str(item.get("detail", ""))[:500], run_id, when),
        )
        self.conn.commit()

    def log_run(self, row: dict) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO runs VALUES (:run_id,:started_at,:mode,:queries,:candidates,:qualified,"
            ":duplicates,:rejected,:error_count,:error_details,:email_status)", row)
        self.conn.commit()

    def runs(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT 50")]

    def set_outreach_status(self, dedupe_key: str, status: str) -> None:
        self.conn.execute("UPDATE leads SET outreach_status=? WHERE dedupe_key=?", (status, dedupe_key))
        self.conn.commit()
