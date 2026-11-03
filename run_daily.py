"""Command-line entry point (used by GitHub Actions / cron).

  python run_daily.py              # dry run: searches, scores, emails you; stores nothing
  python run_daily.py --live       # stores leads in SQLite and logs the run
"""
from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from leadgen.config import load_settings  # noqa: E402
from leadgen.db import DB  # noqa: E402
from leadgen.export import master_xlsx, new_leads_xlsx  # noqa: E402
from leadgen.pipeline import log_run, run_pipeline  # noqa: E402
from leadgen.report import build_summary, send_email  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily lead generation run")
    ap.add_argument("--live", action="store_true", help="store leads and log the run (default: dry run)")
    ap.add_argument("--no-email", action="store_true", help="do not send the summary email")
    ap.add_argument("--max-queries", type=int, default=None)
    ap.add_argument("--max-candidates", type=int, default=None)
    args = ap.parse_args()

    settings = load_settings()
    try:
        result = run_pipeline(settings, live=args.live, max_queries=args.max_queries,
                              max_candidates=args.max_candidates, log=print)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    fresh = result.qualified
    attachments = [
        (f"leads-{result.started_at[:10]}{'' if args.live else '-TEST'}.xlsx", new_leads_xlsx(fresh)),
        (f"master-leads-{result.started_at[:10]}.xlsx", master_xlsx(result.existing_rows, fresh, args.live)),
    ]
    email_status = "skipped (--no-email)"
    if not args.no_email:
        subject, html = build_summary(result, settings)
        email_status = send_email(settings, subject, html, attachments)
    log_run(settings, result, email_status)

    print(f"\nRun {result.run_id} ({'LIVE' if args.live else 'dry run'}): "
          f"{result.count('qualified')} qualified, {result.count('duplicate')} duplicates, "
          f"{result.count('rejected')} rejected, {len(result.errors)} errors. Email: {email_status}")
    for e in result.errors[:10]:
        print("  error:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
