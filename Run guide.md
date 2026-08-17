# How to Run — Two Paths

Both paths need the model server running first. Always start this, in its own terminal:

```powershell
cd C:\llama
.\llama-server.exe -m models\Qwen3.5-9B-Q4_K_M.gguf --port 8080 --host 0.0.0.0 -ngl 999 --ctx-size 4096 --parallel 1
```

Verify it's up:
```powershell
curl.exe http://localhost:8080/health
```

---

## Path A — Terminal only (no dashboard)

```powershell
docker compose up -d postgres
docker compose exec postgres psql -U jmp_user -d job_market -c "TRUNCATE TABLE postings CASCADE;"
docker compose up --build *>&1 | Tee-Object -FilePath ".\pipeline_run_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
```

- Truncate step is optional — skip it if you want to keep accumulating data instead of a fresh run.
- Full command reference: `COMMANDS.md`.

---

## Path B — With the dashboard UI

**One-time setup:**
```powershell
pip install -r requirements-dashboard.txt
```

**Every time you want the dashboard:**
```powershell
streamlit run src/dashboard/app.py
```

Opens at `http://localhost:8501`. From there:
1. Click **"Check llama-server health"** to confirm the model is reachable.
2. (Optional) Check the truncate confirm box and click **"Truncate postings table"** for a clean run.
3. Set `SCRAPER_MAX_PER_SOURCE` (or leave at 25 for a quick test).
4. Click **"Run Full Pipeline"** — logs stream live in the page.
5. Browse results in the **Raw Scraped Data**, **Extraction Before/After**, and **Final Results** tabs.

No terminal commands needed once Streamlit is running — everything after that is buttons.

---

## Notes

- Postgres must be running (`docker compose up -d postgres`) before either path can query or truncate data.
- The dashboard runs on your **host**, not in Docker — it shells out to `docker compose` directly, same as Path A.
- Google Sheet gets written either way, at the end of a full pipeline run (Path A's `docker compose up`, or Path B's "Run Full Pipeline" button — both trigger the same `sheets-writer` stage).