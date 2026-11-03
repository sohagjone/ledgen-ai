"""Streamlit dashboard for the lead-generation pipeline."""
from __future__ import annotations

import hmac

import pandas as pd
import streamlit as st

from leadgen.config import _get, load_settings
from leadgen.db import DB
from leadgen.export import master_xlsx, new_leads_xlsx, to_xlsx
from leadgen.pipeline import log_run, run_pipeline
from leadgen.report import build_summary, send_email

st.set_page_config(page_title="Lead Generation", page_icon="📈", layout="wide")


def gate() -> None:
    """Simple password gate. Set APP_PASSWORD in secrets; the app refuses to show data without it."""
    expected = _get("APP_PASSWORD")
    if not expected:
        st.error("APP_PASSWORD is not set. Add it to your Streamlit secrets before using this app.")
        st.stop()
    if st.session_state.get("authed"):
        return
    pw = st.text_input("Password", type="password")
    if pw and hmac.compare_digest(pw, expected):
        st.session_state["authed"] = True
        st.rerun()
    elif pw:
        st.error("Wrong password")
    st.stop()


gate()
settings = load_settings()
st.title("📈 Market Research Lead Generation")

tab_run, tab_leads, tab_drafts, tab_log = st.tabs(["Run", "Leads", "Outreach drafts", "Run log"])

# ------------------------------------------------------------------ Run
with tab_run:
    missing = settings.missing_for_run()
    if missing:
        st.warning("Add these secrets first: " + ", ".join(missing))
    c1, c2, c3 = st.columns(3)
    live = c1.toggle("Live mode (store leads)", value=False,
                     help="Off = dry run: searches and scores but writes nothing. On Streamlit Cloud, stored data "
                          "is lost when the app restarts - use the GitHub Actions daily run for persistent storage.")
    n_queries = c2.slider("Search queries", 1, 12, 2)
    n_cands = c3.slider("Max pages to analyse", 1, 25, 3)
    send_mail = st.checkbox("Email me the summary + Excel files", value=False)

    if st.button("Run discovery", type="primary", disabled=bool(missing)):
        lines: list[str] = []
        with st.status("Running pipeline...", expanded=True) as status:
            box = st.empty()

            def log(msg: str) -> None:
                lines.append(msg)
                box.code("\n".join(lines[-12:]))

            try:
                result = run_pipeline(settings, live=live, max_queries=n_queries, max_candidates=n_cands, log=log)
                status.update(label="Done", state="complete")
                st.session_state["result"] = result
            except Exception as exc:  # show any failure instead of a stack trace
                status.update(label="Failed", state="error")
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
            st.info(f"Email: {email_status}")
        log_run(settings, result, email_status)

    result = st.session_state.get("result")
    if result:
        st.subheader(f"Run {result.run_id} - {'LIVE' if result.live else 'dry run'}")
        m = st.columns(5)
        m[0].metric("Results seen", result.raw_results)
        m[1].metric("Analysed", len(result.items))
        m[2].metric("Qualified", result.count("qualified"))
        m[3].metric("Duplicates", result.count("duplicate"))
        m[4].metric("Errors", len(result.errors))
        fresh = result.qualified
        if fresh:
            df = pd.DataFrame(fresh)[["score", "company_name", "website", "industry", "country",
                                      "contact_name", "business_email", "reason", "source_url"]]
            st.dataframe(df, use_container_width=True, hide_index=True)
            d1, d2 = st.columns(2)
            d1.download_button("⬇ New leads (.xlsx)", new_leads_xlsx(fresh), "new-leads.xlsx")
            d2.download_button("⬇ Master sheet (.xlsx)", master_xlsx(result.existing_rows, fresh, result.live),
                               "master-leads.xlsx")
        else:
            st.info("No new qualified leads this run.")
        if result.errors:
            with st.expander(f"Errors and failed requests ({len(result.errors)})"):
                for e in result.errors:
                    st.write("- " + e)

# ------------------------------------------------------------------ Leads
with tab_leads:
    db = DB(settings.db_path)
    rows = db.leads()
    db.close()
    if not rows:
        st.info("No stored leads yet. Run the pipeline in live mode (or the daily GitHub Action).")
    else:
        df = pd.DataFrame(rows)
        f1, f2, f3 = st.columns(3)
        min_s = f1.slider("Minimum score", 0, 100, 0)
        countries = f2.multiselect("Country", sorted(df["country"].dropna().unique()))
        only_email = f3.checkbox("Only leads with a published email")
        view = df[df["score"] >= min_s]
        if countries:
            view = view[view["country"].isin(countries)]
        if only_email:
            view = view[view["business_email"] != "Not found"]
        st.caption(f"{len(view)} of {len(df)} leads")
        st.dataframe(view[["score", "company_name", "website", "industry", "country", "contact_name",
                           "contact_title", "business_email", "reason", "discovered_at", "source_url"]],
                     use_container_width=True, hide_index=True)
        st.download_button("⬇ Master sheet (.xlsx)", to_xlsx(view.to_dict("records"), "All Leads"),
                           "master-leads.xlsx")
        with st.expander("Verified facts vs assumptions"):
            pick = st.selectbox("Lead", view["company_name"].tolist()) if len(view) else None
            if pick:
                r = view[view["company_name"] == pick].iloc[0]
                st.markdown("**Verified facts**\n\n" + "\n".join("- " + x for x in str(r["verified_facts"]).split(" | ") if x))
                st.markdown("**Assumptions (unverified)**\n\n" + "\n".join("- " + x for x in str(r["assumptions"]).split(" | ") if x))
                st.caption(r["score_breakdown"])

# ------------------------------------------------------------------ Drafts
with tab_drafts:
    st.caption("Drafts are never sent by this app. Review, copy, and send them yourself - and check the "
               "anti-spam rules that apply to the recipient (CAN-SPAM, CASL, UK PECR/GDPR, Australian Spam Act).")
    db = DB(settings.db_path)
    drafted = [r for r in db.leads() if r["outreach_draft"]]
    if not drafted:
        st.info("No drafts stored yet.")
    else:
        names = [f'{r["company_name"]} (score {r["score"]}) - {r["outreach_status"]}' for r in drafted]
        idx = st.selectbox("Draft", range(len(drafted)), format_func=lambda i: names[i])
        r = drafted[idx]
        st.text_area("Draft", r["outreach_draft"], height=320)
        st.write(f'Contact: {r["contact_name"]} | Email: {r["business_email"]} | [Source]({r["source_url"]})')
        b1, b2, b3 = st.columns(3)
        if b1.button("Mark approved (I will send it myself)"):
            db.set_outreach_status(r["dedupe_key"], "Approved - to be sent manually")
            st.rerun()
        if b2.button("Mark sent manually"):
            db.set_outreach_status(r["dedupe_key"], "Sent manually")
            st.rerun()
        if b3.button("Discard"):
            db.set_outreach_status(r["dedupe_key"], "Discarded")
            st.rerun()
    db.close()

# ------------------------------------------------------------------ Run log
with tab_log:
    db = DB(settings.db_path)
    runs = db.runs()
    db.close()
    st.dataframe(pd.DataFrame(runs), use_container_width=True, hide_index=True) if runs else st.info("No live runs logged yet.")
