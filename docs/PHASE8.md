# Phase 8 — Google Sheets Reporting

## What this phase is, in plain language

All the analysis in the world doesn't matter if it stays locked in a database
only you can query with SQL. This phase publishes the ranked, scored results
somewhere you (or anyone) can actually look at them — a spreadsheet, refreshed
automatically.

## What we built

- **`src/automation/sheets_writer.py`** — pulls the top N postings by
  `fit_score`, clears and rewrites a Google Sheet with a clean set of columns,
  and marks those postings `reported_at` in the database so you can
  distinguish "already reported" from "new since last report" later if needed.

## Key concept: service account, not OAuth login

A human clicking through a Google consent screen doesn't work for something
that runs unattended on a schedule at 3am. A service account is a
machine-identity: it has its own email address, its own credentials file, and
you explicitly share a specific sheet with it — least-privilege by design (it
can only touch sheets you've deliberately shared, nothing else in your Drive).

## One-time setup (do this once, outside the codebase)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → create a
   project (or reuse one).
2. Enable the **Google Sheets API** and **Google Drive API** for that project.
3. Create a **Service Account** (IAM & Admin → Service Accounts → Create).
4. Create a JSON key for it, download it, save as `credentials.json` in the
   repo root (already gitignored — never commit it).
5. Open the JSON file, copy the `client_email` value.
6. Create (or open) the Google Sheet you want reports written to, click
   **Share**, and share it with that `client_email` address (Editor access).
7. Set `GOOGLE_SHEET_NAME` in `.env` to match that sheet's name exactly.

Run `docker compose run --rm sheets-writer` after this — it creates the sheet
if it doesn't exist yet (as long as the service account has permission), or
writes into the one you shared.
