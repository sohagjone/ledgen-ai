"""Streamlit dashboard for the lead-generation pipeline."""
from __future__ import annotations

import hmac

import pandas as pd
import streamlit as st

from leadgen.config import _get, load_settings
from leadgen.db import DB
from leadgen.export import analysis_xlsx, master_xlsx, new_leads_xlsx, to_xlsx
from leadgen.pipeline import log_run, run_pipeline
from leadgen.report import build_summary, send_email
from leadgen.search import COUNTRY_LABELS, DEFAULT_SIGNALS, SIGNALS, describe_focus
from leadgen.ui import CSS, hero, kpis, lead_card

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

st.set_page_config(page_title="Lead Finder", page_icon="📈", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)


def gate() -> None:
    """Password gate. Set APP_PASSWORD in secrets; without it the app refuses to show data."""
    expected = _get("APP_PASSWORD")
    if not expected:
        st.error("APP_PASSWORD is not set. Add it to your Streamlit secrets before using this app.")
        st.stop()
    if st.session_state.get("authed"):
        return
    st.markdown(hero("Lead Finder", "Sign in to continue", []), unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        pw = st.text_input("Password", type="password")
        if pw and hmac.compare_digest(pw, expected):
            st.session_state["authed"] = True
            st.rerun()
        elif pw:
            st.error("Wrong password")
    st.stop()


gate()
settings = load_settings()

st.markdown(hero(
    "Market Research Lead Finder",
    "Discover companies that need market research, competitor analysis and market-entry insight - scored, verified and ready to export.",
    ["Public sources only", "Every contact field verified", "Drafts never auto-sent", "Excel export"],
), unsafe_allow_html=True)

tab_find, tab_db, tab_drafts, tab_log = st.tabs(["🔍 Find leads", "📚 Lead database", "✉️ Outreach drafts", "🧾 Run log"])

# =============================================================== FIND LEADS
with tab_find:
    missing = settings.missing_for_run()
    if missing:
        st.warning("Add these secrets before running: " + ", ".join(missing))

    with st.form("search"):
        st.markdown('<div class="section-title">What are you looking for?</div>'
                    '<div class="hint">Describe the industry you want to reach. Leave blank for a general search.</div>',
                    unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        industry = c1.text_input("Industry / niche", placeholder="e.g. fintech, e-commerce fashion, HR software, solar energy")
        keywords = c2.text_input("Extra keywords (optional)", placeholder="e.g. Series A, subscription, B2B, DTC")
        c3, c4 = st.columns(2)
        countries = c3.multiselect("Countries", list(COUNTRY_LABELS), default=list(COUNTRY_LABELS),
                                   format_func=lambda c: COUNTRY_LABELS[c])
        signals = c4.multiselect("Buying signals to look for", list(SIGNALS), default=DEFAULT_SIGNALS,
                                 format_func=lambda k: SIGNALS[k][0])
        c5, c6 = st.columns(2)
        n_queries = c5.slider("Search depth (queries)", 1, 12, 4,
                              help="More queries = more candidate companies, but a longer run.")
        n_cands = c6.slider("Max pages to analyse", 1, 25, 8)
        o1, o2 = st.columns(2)
        live = o1.toggle("Save leads to the database (live mode)", value=False,
                         help="Off = preview only, nothing is saved. On Streamlit Cloud, saved data is temporary "
                              "- the daily GitHub Action keeps the permanent copy. Always download the Excel file.")
        send_mail = o2.toggle("Email me the summary + Excel files", value=False)
        submitted = st.form_submit_button("🔍  Find leads", use_container_width=True, disabled=bool(missing))

    if submitted:
        lines: list[str] = []
        with st.status("Searching, reading pages and scoring leads...", expanded=True) as status:
            box = st.empty()

            def log(msg: str) -> None:
                lines.append(msg)
                box.code("\n".join(lines[-10:]), language=None)

            try:
                result = run_pipeline(settings, live=live, max_queries=n_queries, max_candidates=n_cands, log=log,
                                      industry=industry, keywords=keywords, countries=countries, signals=signals)
                status.update(label="Search complete", state="complete", expanded=False)
            except Exception as exc:
                status.update(label="Run failed", state="error")
                st.error(str(exc))
                st.stop()
        email_status = "not requested"
        if send_mail:
            subject, html = build_summary(result, settings)
            fresh = result.qualified
            email_status = send_email(settings, subject, html, [
                ("leads.xlsx", new_leads_xlsx(fresh)),
                ("master-leads.xlsx", master_xlsx(result.existing_rows, fresh, live)),
            ])
        log_run(settings, result, email_status)
        st.session_state["result"] = result
        st.session_state["email_status"] = email_status

    result = st.session_state.get("result")
    if result:
        focus = describe_focus(result.criteria.get("industry", ""), result.criteria.get("keywords", "")) or "general search"
        st.markdown(f'<div class="section-title" style="margin-top:18px">Results - {focus}</div>'
                    f'<div class="hint">Run {result.run_id} · {"saved to database" if result.live else "preview only (nothing saved)"}'
                    f'</div>', unsafe_allow_html=True)
        st.markdown(kpis([
            ("Search results seen", result.raw_results, ""),
            ("Pages analysed", len(result.items), ""),
            ("Qualified leads", result.count("qualified"), "good"),
            ("Duplicates", result.count("duplicate"), ""),
            ("Errors", len(result.errors), "bad" if result.errors else ""),
        ]), unsafe_allow_html=True)

        fresh = result.qualified
        # ---- downloads (always shown after a run)
        st.markdown('<div class="section-title">⬇ Download Excel</div>', unsafe_allow_html=True)
        d1, d2, d3 = st.columns(3)
        d1.download_button("New leads (.xlsx)", new_leads_xlsx(fresh), f"new-leads-{result.started_at[:10]}.xlsx",
                           XLSX_MIME, use_container_width=True, key="dl_new")
        d2.download_button("Master sheet - all leads (.xlsx)", master_xlsx(result.existing_rows, fresh, result.live),
                           f"master-leads-{result.started_at[:10]}.xlsx", XLSX_MIME, use_container_width=True, key="dl_master")
        d3.download_button("Full analysis incl. rejected (.xlsx)", analysis_xlsx(result.items),
                           f"analysis-{result.started_at[:10]}.xlsx", XLSX_MIME, use_container_width=True, key="dl_analysis")
        es = st.session_state.get("email_status", "not requested")
        if es not in ("not requested",):
            (st.success if es == "sent" else st.warning)(f"Email: {es}")

        if fresh:
            st.markdown('<div class="section-title" style="margin-top:14px">New qualified leads</div>', unsafe_allow_html=True)
            for l in fresh:
                st.markdown(lead_card(l), unsafe_allow_html=True)
                with st.expander(f"Details - {l['company_name']}"):
                    a, b = st.columns(2)
                    a.markdown("**Verified facts**\n\n" + ("\n".join("- " + x for x in str(l["verified_facts"]).split(" | ") if x) or "_none_"))
                    b.markdown("**Assumptions (unverified)**\n\n" + ("\n".join("- " + x for x in str(l["assumptions"]).split(" | ") if x) or "_none_"))
                    st.caption("Score breakdown: " + str(l["score_breakdown"]))
                    if l["outreach_draft"]:
                        st.text_area("Outreach draft (not sent)", l["outreach_draft"], height=240, key=f"d_{l['dedupe_key']}")
        else:
            st.info("No new qualified leads for this search. Try a broader industry, more countries, or more queries. "
                    "The 'Full analysis' download shows why each page was rejected.")
        if result.errors:
            with st.expander(f"Errors and failed requests ({len(result.errors)})"):
                for e in result.errors:
                    st.write("- " + e)

# =============================================================== LEAD DATABASE
with tab_db:
    db = DB(settings.db_path)
    rows = db.leads()
    db.close()
    if not rows:
        st.info("No saved leads yet. Run a search with 'Save leads' switched on, or wait for the daily GitHub Action.")
    else:
        df = pd.DataFrame(rows)
        st.markdown(kpis([
            ("Saved leads", len(df), ""),
            ("Avg score", round(df["score"].mean()), ""),
            ("With email", int((df["business_email"] != "Not found").sum()), "good"),
            ("Countries", df["country"].nunique(), ""),
            ("Drafts", int(df["outreach_draft"].astype(bool).sum()), ""),
        ]), unsafe_allow_html=True)
        f1, f2, f3, f4 = st.columns([1.2, 1.4, 1.4, 1])
        text = f1.text_input("Search", placeholder="company, industry, reason...")
        min_s = f2.slider("Minimum score", 0, 100, 0)
        countries_f = f3.multiselect("Country", sorted(df["country"].dropna().unique()))
        only_email = f4.checkbox("Has email")
        view = df[df["score"] >= min_s]
        if text:
            t = text.lower()
            view = view[view.apply(lambda r: t in " ".join(str(r[c]).lower() for c in
                                  ("company_name", "industry", "reason", "country", "website")), axis=1)]
        if countries_f:
            view = view[view["country"].isin(countries_f)]
        if only_email:
            view = view[view["business_email"] != "Not found"]
        view = view.sort_values("score", ascending=False)
        st.caption(f"Showing {len(view)} of {len(df)} leads")
        g1, g2 = st.columns(2)
        g1.download_button("⬇ Download filtered view (.xlsx)", to_xlsx(view.to_dict("records"), "Leads"),
                           "leads-filtered.xlsx", XLSX_MIME, use_container_width=True, key="dl_view")
        g2.download_button("⬇ Download ALL saved leads (.xlsx)", to_xlsx(df.to_dict("records"), "All Leads"),
                           "leads-all.xlsx", XLSX_MIME, use_container_width=True, key="dl_all")
        st.dataframe(view[["score", "company_name", "website", "industry", "country", "contact_name",
                           "business_email", "reason", "discovered_at"]], use_container_width=True, hide_index=True)
        for l in view.head(15).to_dict("records"):
            st.markdown(lead_card(l), unsafe_allow_html=True)

# =============================================================== DRAFTS
with tab_drafts:
    st.markdown('<div class="hint">Drafts are never sent by this app. Review, copy and send them yourself - and check the '
                'anti-spam rules for the recipient (CAN-SPAM, CASL, UK PECR/GDPR, Australian Spam Act).</div>',
                unsafe_allow_html=True)
    db = DB(settings.db_path)
    drafted = [r for r in db.leads() if r["outreach_draft"]]
    if not drafted:
        st.info("No drafts saved yet.")
    else:
        names = [f'{r["company_name"]} (score {r["score"]}) - {r["outreach_status"]}' for r in drafted]
        idx = st.selectbox("Draft", range(len(drafted)), format_func=lambda i: names[i])
        r = drafted[idx]
        st.text_area("Draft", r["outreach_draft"], height=320)
        st.write(f'Contact: {r["contact_name"]} | Email: {r["business_email"]} | [Source]({r["source_url"]})')
        b1, b2, b3 = st.columns(3)
        if b1.button("Mark approved (I'll send it myself)", use_container_width=True):
            db.set_outreach_status(r["dedupe_key"], "Approved - to be sent manually")
            st.rerun()
        if b2.button("Mark sent manually", use_container_width=True):
            db.set_outreach_status(r["dedupe_key"], "Sent manually")
            st.rerun()
        if b3.button("Discard", use_container_width=True):
            db.set_outreach_status(r["dedupe_key"], "Discarded")
            st.rerun()
    db.close()

# =============================================================== RUN LOG
with tab_log:
    db = DB(settings.db_path)
    runs = db.runs()
    db.close()
    if runs:
        st.dataframe(pd.DataFrame(runs), use_container_width=True, hide_index=True)
    else:
        st.info("No saved runs logged yet.")

st.markdown('<div class="footer">Verified fields come only from public source text · unsupported fields are shown as "Not found" · '
            "nothing is sent automatically</div>", unsafe_allow_html=True)
