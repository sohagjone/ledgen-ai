import io

import openpyxl

from leadgen.config import Settings
from leadgen.db import DB
from leadgen.enrich import best_email, extract_emails
from leadgen.export import master_xlsx, new_leads_xlsx
from leadgen.verify import Known, verify_and_score


def settings(**kw):
    base = dict(anthropic_api_key="k", brave_api_key="b", model="m", smtp_user="", smtp_password="",
                notify_email="x@y.z", sender_name="Me", postal_address="1 Main St", opt_out_line="reply no thanks",
                min_score=50, draft_min_score=65, max_queries=2, max_candidates=3, max_enrich=3,
                db_path=":memory:", user_agent="t")
    base.update(kw)
    return Settings(**base)


SRC = {"source_url": "https://news.example.com/acme-canada", "source_domain": "news.example.com",
       "title": "Acme expands into Canada", "snippet": "Acme Corp announced expansion. CEO Jane Doe said hello."}
PAGE = ("Acme Corp (acme.com) announced expansion into Canada. CEO Jane Doe said it is exciting. "
        "Contact partners@acme.com or follow https://www.linkedin.com/in/janedoe")


def raw(**kw):
    r = {"is_target_company": True, "company_name": "Acme Corp", "website": "https://acme.com", "industry": "SaaS",
         "country": "Canada", "company_size": "Not found", "contact_name": "Jane Doe", "contact_title": "CEO",
         "business_email": "partners@acme.com", "linkedin_url": "https://www.linkedin.com/in/janedoe",
         "reason_for_fit": "Expanding", "verified_facts": ["Expands into Canada"], "assumptions": [],
         "fit_score": 25, "signal_score": 20, "role_score": 14, "size_industry_score": 10,
         "qualification_notes": "n", "outreach_subject": "Canada", "outreach_body": "x" * 80}
    r.update(kw)
    return r


def run(r, known=None, **kw):
    return verify_and_score(r, SRC, PAGE, True, settings(**kw), known or Known(), "run1")


def test_verified_fields_kept_and_scored():
    lead = run(raw())
    assert lead["status"] == "qualified"
    assert lead["business_email"] == "partners@acme.com"
    assert lead["linkedin_url"].endswith("janedoe")
    assert lead["contact_name"] == "Jane Doe"
    assert 0 < lead["score"] <= 100
    assert lead["outreach_status"].startswith("DRAFT")
    assert "reply no thanks" in lead["outreach_draft"] and "1 Main St" in lead["outreach_draft"]


def test_fabricated_fields_are_discarded():
    lead = run(raw(business_email="ceo@acme.com", contact_name="John Smith",
                   linkedin_url="https://linkedin.com/in/made-up", website="https://invented.io"))
    assert lead["business_email"] == "Not found"
    assert lead["contact_name"] == "Not found" and lead["contact_title"] == "Not found"
    assert lead["linkedin_url"] == "Not found"
    assert lead["website"] == "Not found"
    assert "discarded" in lead["assumptions"]


def test_free_mail_and_foreign_domain_email_rejected():
    assert run(raw(business_email="jane@gmail.com"))["business_email"] == "Not found"


def test_non_target_and_low_score_rejected():
    assert run(raw(is_target_company=False, rejection_reason="listicle"))["status"] == "rejected"
    low = run(raw(fit_score=0, signal_score=0, role_score=0, size_industry_score=0, business_email="Not found",
                  contact_name="Not found", linkedin_url="Not found"), min_score=90)
    assert low["status"] == "rejected" and "threshold" in low["detail"]


def test_no_draft_below_threshold():
    assert run(raw(), draft_min_score=100)["outreach_draft"] == ""


def test_geography_penalty():
    inside, outside = run(raw(country="Canada")), run(raw(country="Other: Japan"))
    assert outside["score"] == inside["score"] - 15


def test_dedupe_by_domain_name_and_email():
    known = Known()
    assert run(raw(), known)["status"] == "qualified"
    assert run(raw(), known)["status"] == "duplicate"  # same domain
    by_name = run(raw(website="Not found", business_email="Not found"), Known.from_rows([{"company_name": "Acme Corp"}]))
    assert by_name["status"] == "duplicate"            # same company name, different key
    by_email = run(raw(), Known.from_rows([{"business_email": "partners@acme.com", "domain": "other.com"}]))
    assert by_email["status"] == "duplicate"


def test_extract_emails_only_company_domain():
    text = "Mail us: <a href='mailto:Hello@Acme.com'>x</a> or sales@acme.com. logo@acme.com.png jane@gmail.com bob@other.com"
    assert extract_emails(text, "acme.com") == ["hello@acme.com", "sales@acme.com"]


def test_best_email_prefers_named_contact_then_roles():
    c = [("info@acme.com", "u1"), ("jane.doe@acme.com", "u2"), ("sales@acme.com", "u3")]
    assert best_email(c, "Jane Doe")[0] == "jane.doe@acme.com"
    assert best_email([("support@acme.com", "u"), ("hello@acme.com", "u")], "")[0] == "hello@acme.com"
    assert best_email([], "x") is None


def test_db_insert_unique_and_processed(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    lead = run(raw())
    assert db.insert_lead(lead) is True
    assert db.insert_lead(lead) is False
    db.mark_processed(lead, "run1", "now")
    assert "https://news.example.com/acme-canada" in db.processed_urls()
    db.set_outreach_status(lead["dedupe_key"], "Discarded")
    assert db.leads()[0]["outreach_status"] == "Discarded"


def test_excel_exports_open_and_have_expected_columns():
    lead = run(raw())
    wb = openpyxl.load_workbook(io.BytesIO(new_leads_xlsx([lead])))
    ws = wb["New Leads"]
    headers = [c.value for c in ws[1]]
    assert "Business Email" in headers and ws.max_row == 2
    wb2 = openpyxl.load_workbook(io.BytesIO(master_xlsx([lead], [lead], live=False)))
    ws2 = wb2["All Leads"]
    assert ws2["A1"].value == "Record" and ws2.max_row == 3
    assert ws2["A2"].value.startswith("NEW - TEST")
    empty = openpyxl.load_workbook(io.BytesIO(new_leads_xlsx([])))["New Leads"]
    assert "No new qualified" in str(empty["A2"].value)
