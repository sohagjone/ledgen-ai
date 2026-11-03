from __future__ import annotations

from io import BytesIO

import pandas as pd

HEADERS = {
    "score": "Score", "company_name": "Company", "website": "Website", "industry": "Industry",
    "country": "Country", "company_size": "Company Size", "contact_name": "Contact Name",
    "contact_title": "Contact Title", "business_email": "Business Email", "linkedin_url": "LinkedIn",
    "reason": "Why It Fits", "score_breakdown": "Score Breakdown", "verified_facts": "Verified Facts",
    "assumptions": "Assumptions", "source_url": "Source URL", "discovered_at": "Discovered",
    "outreach_status": "Outreach Status", "outreach_draft": "Outreach Draft",
}


def _frame(rows: list[dict], tag_col: str | None = None) -> pd.DataFrame:
    cols = list(HEADERS)
    data = []
    for r in rows:
        rec = {HEADERS[c]: r.get(c, "") for c in cols}
        if tag_col:
            rec = {"Record": r.get("_tag", ""), **rec}
        data.append(rec)
    return pd.DataFrame(data)


def to_xlsx(rows: list[dict], sheet_name: str, tag_col: bool = False, empty_note: str = "No leads") -> bytes:
    """Build an .xlsx in memory: frozen header, filters, sensible column widths."""
    df = _frame(rows, "tag" if tag_col else None) if rows else pd.DataFrame([{"Note": empty_note}])
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name=sheet_name)
        ws = xw.sheets[sheet_name]
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:
            longest = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(max(10, longest + 2), 60)
    return buf.getvalue()


def new_leads_xlsx(rows: list[dict]) -> bytes:
    return to_xlsx(rows, "New Leads", empty_note="No new qualified leads this run")


def master_xlsx(existing: list[dict], fresh: list[dict], live: bool) -> bytes:
    tag = "NEW this run" if live else "NEW - TEST (not stored)"
    rows = [{**r, "_tag": tag} for r in fresh] + [{**r, "_tag": "Stored"} for r in existing]
    return to_xlsx(rows, "All Leads", tag_col=True, empty_note="No leads stored yet")
