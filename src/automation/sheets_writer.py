"""
Writes the current top-ranked postings to a Google Sheet. Uses a service account
(credentials.json, gitignored, mounted read-only into the container — see
docker-compose.yml) rather than OAuth user flow, since this runs unattended on
a schedule with no one available to click through a browser consent screen.

Setup (one-time, documented in docs/PHASE8.md):
  1. Create a Google Cloud service account, enable Sheets + Drive API.
  2. Download its JSON key as credentials.json in the repo root.
  3. Create your target Google Sheet yourself and share it with the service
     account's email address (Editor access).
  4. Set GOOGLE_SHEET_ID in .env to the sheet's ID (from its URL:
     .../spreadsheets/d/<ID>/edit).

Run: python -m src.automation.sheets_writer

CHANGE 2026-08-16: was opening by name (client.open(name)) with a
client.create(name) fallback if not found. Two real problems with that:
  1. Drive's name-search doesn't reliably surface spreadsheets that were only
     shared with the service account (not owned by it) — it returned
     SpreadsheetNotFound even though the sheet was correctly shared.
  2. The create() fallback can NEVER succeed for a service account — Google
     enforces a 0-byte personal Drive storage quota on them, so "create a
     replacement sheet" always fails with a quota error. That's a platform
     restriction, not something retryable.
Opening by ID sidesteps both issues entirely, and is the standard approach
for service-account access to a human-owned, human-shared sheet.
"""
from __future__ import annotations

import datetime as dt

import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy import select, update

from src.automation.run_logger import run_stage
from src.common.config import get_settings
from src.common.db import session_scope
from src.common.logging import configure_logging, get_logger
from src.common.models import Posting

logger = get_logger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

HEADER = [
    "Fit Score",
    "Title",
    "Company",
    "Category",
    "Seniority",
    "Remote/Onsite",
    "Location",
    "Salary Min",
    "Salary Max",
    "Skills",
    "Source",
    "URL",
]


def _row_for(posting: Posting) -> list:
    return [
        posting.fit_score,
        posting.title or "",
        posting.company or "",
        posting.category_label or "",
        posting.seniority or "",
        posting.remote_or_onsite or "",
        posting.location or "",
        posting.salary_min or "",
        posting.salary_max or "",
        ", ".join(posting.required_skills or []),
        posting.source,
        posting.url,
    ]


def get_client() -> gspread.Client:
    settings = get_settings()
    creds = Credentials.from_service_account_file(
        settings.google_sheets_credentials_path, scopes=SCOPES
    )
    return gspread.authorize(creds)


def _open_sheet(client: gspread.Client) -> gspread.Worksheet:
    settings = get_settings()

    if settings.google_sheet_id:
        return client.open_by_key(settings.google_sheet_id).sheet1

    # No ID configured — fall back to name search, but fail with a clear,
    # actionable message rather than attempting client.create() (guaranteed
    # to fail for a service account — see module docstring).
    try:
        return client.open(settings.google_sheet_name).sheet1
    except gspread.SpreadsheetNotFound as exc:
        raise RuntimeError(
            f"Could not find a spreadsheet named '{settings.google_sheet_name}' "
            "via Drive search, and no GOOGLE_SHEET_ID is set in .env. Service "
            "accounts cannot create their own spreadsheets (Google enforces a "
            "0-byte Drive quota for them), so this must be created and shared "
            "by you: create the sheet, share it with the service account's "
            "email (Editor access), then set GOOGLE_SHEET_ID in .env to the "
            "ID from its URL (.../spreadsheets/d/<ID>/edit)."
        ) from exc


def run(top_n: int = 200) -> None:
    configure_logging()
    with run_stage("sheets_writer") as run_ctx:
        with session_scope() as session:
            # CHANGED 2026-08-16: added cluster_id.is_not(None) as a second,
            # independent scope check — not just relying on scorer to have
            # correctly cleared stale fit_score values (which it now does,
            # see src/scoring/main.py, but the final human-facing report
            # shouldn't blindly trust that upstream state is always clean).
            postings = session.scalars(
                select(Posting)
                .where(Posting.fit_score.is_not(None), Posting.cluster_id.is_not(None))
                .order_by(Posting.fit_score.desc())
                .limit(top_n)
            ).all()

            if not postings:
                logger.warning("sheets_writer_no_data", note="Run the scorer first.")
                return

            client = get_client()
            sheet = _open_sheet(client)

            sheet.clear()
            rows = [HEADER] + [_row_for(p) for p in postings]
            sheet.update(rows, value_input_option="USER_ENTERED")

            now = dt.datetime.now(dt.timezone.utc)
            posting_ids = [p.id for p in postings]
            session.execute(
                update(Posting).where(Posting.id.in_(posting_ids)).values(reported_at=now)
            )

            run_ctx.rows_processed = len(postings)
            logger.info("sheets_writer_complete", rows_written=len(postings))


if __name__ == "__main__":
    run()