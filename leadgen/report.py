from __future__ import annotations

import smtplib
from email.message import EmailMessage
from html import escape as esc


def build_summary(result, settings) -> tuple[str, str]:
    """Return (subject, html) for the daily email."""
    leads = sorted([i for i in result.items if i["status"] == "qualified"], key=lambda x: -x["score"])
    rejected = sum(1 for i in result.items if i["status"] == "rejected")
    dups = sum(1 for i in result.items if i["status"] == "duplicate")
    errs = result.errors
    h = ['<div style="font-family:Arial,sans-serif;font-size:14px;color:#222"><h2>Lead generation daily summary</h2>']
    if not result.live:
        h.append('<p style="background:#fff3cd;padding:8px"><b>TEST / DRY RUN</b> - nothing was stored and no outreach was sent.</p>')
    c = getattr(result, "criteria", {}) or {}
    focus = "; ".join(x for x in (f"Industry: {c['industry']}" if c.get("industry") else "",
                                   f"Keywords: {c['keywords']}" if c.get("keywords") else "") if x) or "General (no industry filter)"
    h.append(f"<p><b>Search focus:</b> {esc(focus)}</p>")
    h.append(f"<p>Run {esc(result.run_id)} | {esc(result.started_at)}<br>Queries: {result.queries} | "
             f"Search results seen: {result.raw_results} | New sources analysed: {len(result.items)}<br>"
             f"<b>New qualified leads: {len(leads)}</b> | Rejected: {rejected} | Duplicates: {dups} | Errors: {len(errs)}</p>")
    if leads:
        td = '<td style="border:1px solid #ddd;padding:6px;vertical-align:top">'
        h.append('<table style="border-collapse:collapse;width:100%"><tr>' + "".join(
            f'<th style="text-align:left;border:1px solid #ddd;padding:6px;background:#f5f5f5">{t}</th>'
            for t in ["Score", "Company", "Industry / Country", "Contact", "Why it fits", "Source"]) + "</tr>")
        for l in leads:
            site = (f'<a href="{esc(l["website"])}">{esc(l["company_name"])}</a>'
                    if l["website"] != "Not found" else esc(l["company_name"]))
            contact = "Not found"
            if l["contact_name"] != "Not found":
                contact = f'{esc(l["contact_name"])} ({esc(l["contact_title"])})'
            if l["business_email"] != "Not found":
                contact += f'<br>{esc(l["business_email"])}'
            h.append(f'<tr>{td}<b>{l["score"]}</b><br><small>{esc(l["score_breakdown"])}</small></td>{td}{site}</td>'
                     f'{td}{esc(l["industry"])}<br>{esc(l["country"])}</td>{td}{contact}</td>'
                     f'{td}{esc(l["reason"])}<br><i>Assumptions: {esc(l["assumptions"] or "none")}</i></td>'
                     f'{td}<a href="{esc(l["source_url"])}">source</a></td></tr>')
        h.append("</table>")
    else:
        h.append("<p>No new qualified leads this run.</p>")
    drafts = [l for l in leads if l["outreach_draft"]]
    if drafts:
        h.append("<h3>Outreach drafts for your review (not sent)</h3>")
        for l in drafts:
            h.append(f'<p><b>{esc(l["company_name"])}</b></p><pre style="white-space:pre-wrap;background:#f8f8f8;padding:8px">'
                     f'{esc(l["outreach_draft"])}</pre>')
    if errs:
        h.append(f'<h3 style="color:#b00020">Errors and failed requests ({len(errs)})</h3><ul>'
                 + "".join(f"<li>{esc(e)}</li>" for e in errs[:10]) + "</ul>")
    h.append('<p style="color:#888;font-size:12px">Verified fields come only from the source text; unsupported '
             "fields are Not found. Drafts are never sent automatically.</p></div>")
    subject = ("[TEST] " if not result.live else "") + (
        f"Lead Gen Daily Summary - {len(leads)} new qualified lead(s) - {result.started_at[:10]}"
        + (f" - {len(errs)} error(s)" if errs else ""))
    return subject, "".join(h)


def send_email(settings, subject: str, html: str, attachments: list[tuple[str, bytes]]) -> str:
    """Send via Gmail SMTP (use an App Password). Returns 'sent' or an error string."""
    if not (settings.smtp_user and settings.smtp_password):
        return "skipped: SMTP_USER / SMTP_PASSWORD not configured"
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_user, settings.notify_email, subject
    msg.set_content("This summary needs an HTML-capable email client.")
    msg.add_alternative(html, subtype="html")
    for name, data in attachments:
        msg.add_attachment(data, maintype="application",
                           subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=name)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return "sent"
    except Exception as exc:
        return f"FAILED: {exc}"[:200]
