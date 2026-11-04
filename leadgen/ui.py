"""Presentation helpers for the Streamlit app: CSS and safe HTML snippets.
All dynamic text is HTML-escaped because it originates from scraped web pages."""
from __future__ import annotations

from html import escape as esc

NF = "Not found"

CSS = """
<style>
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1180px;}
html, body, [class*="css"] {font-family: "Inter", "Segoe UI", system-ui, sans-serif;}

.hero {background: linear-gradient(135deg, #0b2447 0%, #19376d 45%, #2a7de1 100%); color: #fff;
  padding: 30px 34px; border-radius: 18px; margin-bottom: 22px; box-shadow: 0 10px 30px rgba(25,55,109,.25);}
.hero h1 {color: #fff; font-size: 2rem; font-weight: 700; margin: 0 0 6px 0; padding: 0; letter-spacing: -.01em;}
.hero p {color: #d6e4ff; margin: 0; font-size: 1.02rem;}
.hero .pill {display: inline-block; background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.28);
  padding: 3px 12px; border-radius: 999px; font-size: .78rem; margin: 14px 8px 0 0;}

.kpis {display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; margin: 6px 0 18px 0;}
.kpi {background: #fff; border: 1px solid #e3e9f2; border-radius: 14px; padding: 14px 16px;
  box-shadow: 0 1px 3px rgba(16,24,40,.05);}
.kpi .v {font-size: 1.7rem; font-weight: 700; color: #19376d; line-height: 1.1;}
.kpi .l {font-size: .78rem; color: #66758c; text-transform: uppercase; letter-spacing: .05em; margin-top: 4px;}
.kpi.good .v {color: #15803d;} .kpi.bad .v {color: #b42318;}

.lead {background: #fff; border: 1px solid #e3e9f2; border-radius: 16px; padding: 18px 20px; margin: 12px 0 4px 0;
  box-shadow: 0 1px 3px rgba(16,24,40,.05); display: flex; gap: 18px; align-items: flex-start;}
.lead .score {min-width: 64px; height: 64px; border-radius: 14px; color: #fff; font-weight: 700; font-size: 1.5rem;
  display: flex; align-items: center; justify-content: center;}
.lead .body {flex: 1; min-width: 0;}
.lead .name {font-size: 1.12rem; font-weight: 650; color: #14213d; margin: 0 0 2px 0;}
.lead .name a {color: #1d4f91; text-decoration: none;}
.lead .meta {color: #66758c; font-size: .86rem; margin-bottom: 8px;}
.lead .why {color: #344256; font-size: .93rem; margin-bottom: 10px;}
.chip {display: inline-block; background: #eef3fb; color: #1d4f91; border-radius: 999px; padding: 3px 11px;
  font-size: .78rem; margin: 0 6px 4px 0;}
.chip.ok {background: #e8f6ee; color: #15803d;} .chip.warn {background: #fff4e0; color: #b45309;}
.chip.muted {background: #f1f4f8; color: #66758c;}

.panel {background: #fff; border: 1px solid #e3e9f2; border-radius: 16px; padding: 18px 20px;
  box-shadow: 0 1px 3px rgba(16,24,40,.05);}
.section-title {font-size: 1.05rem; font-weight: 650; color: #14213d; margin: 4px 0 2px 0;}
.hint {color: #66758c; font-size: .86rem;}

div[data-testid="stTabs"] button[role="tab"] {font-weight: 600; padding: 10px 18px;}
div.stButton > button, div.stDownloadButton > button, div[data-testid="stFormSubmitButton"] > button {
  border-radius: 10px; font-weight: 600; padding: .55rem 1.1rem;}
div[data-testid="stFormSubmitButton"] > button {background: #1d4f91; color: #fff; border: 0;}
div[data-testid="stFormSubmitButton"] > button:hover {background: #163d70; color: #fff;}
div[data-testid="stForm"] {background: #fff; border: 1px solid #e3e9f2; border-radius: 16px; padding: 20px;}
.footer {color: #8795aa; font-size: .8rem; text-align: center; margin-top: 30px;}
@media (max-width: 800px) {.kpis {grid-template-columns: repeat(2, 1fr);} .lead {flex-direction: column;}}
</style>
"""


def hero(title: str, subtitle: str, pills: list[str]) -> str:
    chips = "".join(f'<span class="pill">{esc(p)}</span>' for p in pills)
    return f'<div class="hero"><h1>{esc(title)}</h1><p>{esc(subtitle)}</p>{chips}</div>'


def kpis(items: list[tuple[str, object, str]]) -> str:
    cells = "".join(f'<div class="kpi {cls}"><div class="v">{esc(str(v))}</div><div class="l">{esc(label)}</div></div>'
                    for label, v, cls in items)
    return f'<div class="kpis">{cells}</div>'


def _safe_url(url: str) -> str:
    u = str(url or "").strip()
    return esc(u, quote=True) if u.lower().startswith(("http://", "https://")) else ""


def score_color(score: int) -> str:
    return "#15803d" if score >= 75 else "#c2680c" if score >= 60 else "#64748b"


def lead_card(l: dict) -> str:
    site = _safe_url(l.get("website", ""))
    name = esc(str(l.get("company_name", "")))
    title = f'<a href="{site}" target="_blank" rel="noopener">{name}</a>' if site else name
    meta = " &nbsp;·&nbsp; ".join(esc(str(x)) for x in (l.get("industry"), l.get("country"), l.get("company_size")) if x and x != NF)
    chips = []
    email = l.get("business_email", NF)
    chips.append(f'<span class="chip ok">✉ {esc(email)}</span>' if email != NF else '<span class="chip muted">No published email</span>')
    if l.get("contact_name", NF) != NF:
        chips.append(f'<span class="chip">👤 {esc(l["contact_name"])} · {esc(l.get("contact_title", ""))}</span>')
    li = _safe_url(l.get("linkedin_url", ""))
    if li:
        chips.append(f'<span class="chip"><a href="{li}" target="_blank" rel="noopener">LinkedIn</a></span>')
    if "inferred" in str(l.get("assumptions", "")):
        chips.append('<span class="chip warn">Website inferred - verify</span>')
    if str(l.get("outreach_status", "")).startswith("DRAFT"):
        chips.append('<span class="chip">📝 Draft ready</span>')
    src = _safe_url(l.get("source_url", ""))
    if src:
        chips.append(f'<span class="chip muted"><a href="{src}" target="_blank" rel="noopener">Source</a></span>')
    s = int(l.get("score", 0) or 0)
    return (f'<div class="lead"><div class="score" style="background:{score_color(s)}">{s}</div><div class="body">'
            f'<div class="name">{title}</div><div class="meta">{meta}</div>'
            f'<div class="why">{esc(str(l.get("reason", "")))}</div>{"".join(chips)}</div></div>')
