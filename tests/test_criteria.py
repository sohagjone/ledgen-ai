import io

import openpyxl

from leadgen import qualify as q
from leadgen.export import analysis_xlsx
from leadgen.search import build_queries, clean_text, describe_focus
from leadgen.ui import lead_card


def test_industry_and_keywords_drive_queries():
    qs = build_queries(50, industry="fintech", keywords="Series A", countries=["CA"], signals=["expansion", "funding"])
    assert [x["country"] for x in qs] == ["CA", "CA"]
    assert qs[0]["query"] == "fintech company announces expansion into Canada market Series A"
    assert "raises funding" in qs[1]["query"] and qs[1]["segment"] == "funding"


def test_blank_criteria_fall_back_to_defaults():
    qs = build_queries(50)
    assert len(qs) == 12 and qs[0]["query"].startswith("company announces expansion")
    assert len(build_queries(50, countries=["XX"], signals=["nope"])) == 12   # unknown keys ignored


def test_max_queries_respected_and_at_least_one():
    assert len(build_queries(2, industry="saas")) == 2
    assert len(build_queries(0)) == 1


def test_user_text_is_sanitised():
    assert clean_text('  fin"tech \\ \n\t  ai  ') == "fin tech ai"
    assert len(clean_text("a" * 500)) == 80
    assert describe_focus("HR software", "") == "industry = HR software"
    assert describe_focus("", "") == ""


def test_focus_reaches_the_model_prompt():
    src = {"source_url": "https://x.com/a", "title": "t", "snippet": "s"}
    with_focus = q.build_user_prompt(src, "page", "industry = fintech")
    assert "USER SEARCH FOCUS: industry = fintech" in with_focus and "fit low" in with_focus
    assert "USER SEARCH FOCUS: none" in q.build_user_prompt(src, "page")


def test_lead_card_escapes_scraped_html_and_blocks_bad_links():
    evil = {"company_name": "<script>alert(1)</script>", "website": "javascript:alert(1)", "score": 80,
            "reason": "<img src=x onerror=alert(1)>", "business_email": "a@b.com", "source_url": "https://ok.com/p",
            "linkedin_url": "javascript:evil()", "assumptions": "", "outreach_status": ""}
    html = lead_card(evil)
    assert "<script>" not in html and "<img" not in html and "javascript:" not in html
    assert "&lt;script&gt;" in html and 'href="https://ok.com/p"' in html


def test_analysis_workbook_lists_rejections():
    items = [{"status": "rejected", "detail": "Score 30 below threshold", "score": 30, "company_name": "X",
              "source_url": "https://x"}, {"status": "error", "detail": "HTTP 429", "source_url": "https://y"}]
    ws = openpyxl.load_workbook(io.BytesIO(analysis_xlsx(items)))["Analysis"]
    assert ws["A2"].value == "rejected" and "threshold" in ws["B2"].value and ws.max_row == 3
    assert "Nothing analysed" in str(openpyxl.load_workbook(io.BytesIO(analysis_xlsx([])))["Analysis"]["A2"].value)
