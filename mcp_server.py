"""Optional MCP server so Claude Desktop / Claude Code can drive the pipeline in chat.

Install:  pip install -r requirements-mcp.txt
Run:      python mcp_server.py        (stdio transport)
"""
from __future__ import annotations

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

from leadgen.config import load_settings  # noqa: E402
from leadgen.db import DB  # noqa: E402
from leadgen.export import master_xlsx  # noqa: E402
from leadgen.pipeline import log_run, run_pipeline  # noqa: E402

mcp = FastMCP("lead-generation")


@mcp.tool()
def run_discovery(industry: str = "", keywords: str = "", live: bool = False, max_queries: int = 2,
                  max_candidates: int = 3) -> str:
    """Search for new leads in an industry, qualify and score them. live=False is a dry run that stores nothing."""
    s = load_settings()
    result = run_pipeline(s, live=live, max_queries=max_queries, max_candidates=max_candidates,
                          industry=industry, keywords=keywords)
    log_run(s, result, "not sent (MCP)")
    lines = [f"Run {result.run_id} ({'LIVE' if live else 'dry run'}): {result.count('qualified')} qualified, "
             f"{result.count('duplicate')} duplicates, {result.count('rejected')} rejected, {len(result.errors)} errors"]
    for l in result.qualified:
        lines.append(f"- {l['score']}: {l['company_name']} | {l['website']} | email: {l['business_email']} | {l['reason']}")
    return "\n".join(lines)


@mcp.tool()
def list_leads(min_score: int = 0, limit: int = 20) -> str:
    """List stored leads, highest score first."""
    db = DB(load_settings().db_path)
    rows = sorted([r for r in db.leads() if r["score"] >= min_score], key=lambda r: -r["score"])[:limit]
    db.close()
    if not rows:
        return "No stored leads match."
    return "\n".join(f"{r['score']} | {r['company_name']} | {r['country']} | {r['business_email']} | {r['source_url']}" for r in rows)


@mcp.tool()
def export_master_excel(path: str = "master-leads.xlsx") -> str:
    """Write the cumulative master spreadsheet to `path`."""
    db = DB(load_settings().db_path)
    data = master_xlsx(db.leads(), [], True)
    db.close()
    with open(path, "wb") as fh:
        fh.write(data)
    return f"Wrote {path}"


@mcp.tool()
def set_outreach_status(dedupe_key: str, status: str) -> str:
    """Update a lead's outreach status (e.g. 'Approved - to be sent manually', 'Discarded'). Never sends anything."""
    db = DB(load_settings().db_path)
    db.set_outreach_status(dedupe_key, status)
    db.close()
    return "updated"


if __name__ == "__main__":
    mcp.run()
