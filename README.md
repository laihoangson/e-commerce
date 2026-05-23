## RetailLens

Solo end-to-end e-commerce intelligence platform — a portfolio project targeting Australian tech/retail companies. Demonstrates a generalist DE/DA/DS/MLE skill set across the full data lifecycle, running entirely on $0 free-tier cloud services.

> "See your business through the right lens."

### Data approach

The platform uses 100% synthetically generated Australian e-commerce data via Faker. There is no Olist data in the pipeline — the public Olist Brazilian e-commerce dataset (99k real orders, 2016–2018) is used only as a statistical calibration reference so the synthetic data has realistic distributions.

- Backfill: ~2 years of history (2024-01-01 to 2026-05-30), ~100 orders/day
- Live mode: generates "today's" orders 2x/day via a 12h cron during 2026

### Architecture — Medallion (Bronze -> Silver -> Gold)

- Bronze: 9 raw synthetic tables as DuckDB native TABLEs, each carrying 4 metadata columns (_ingested_at, _source_file, _batch_id, _is_valid)
- Silver: cleansed star schema via dbt — 6 dimensions + 4 facts
- Gold: business marts synced to Supabase Postgres

### Tech stack ($0 free tier)

DuckDB (warehouse) · Supabase Storage + Postgres · dbt · Great Expectations · GitHub Actions · FastAPI on Render · vanilla JS on GitHub Pages · Groq · ChromaDB · UptimeRobot + Slack.

### Status

In active development.

| Phase | Weeks | Milestone | Status |
|-------|-------|-----------|--------|
| 1. Foundation | W1-W2 | Repo, GHA, Supabase, health check | In progress |
| 2. Spec & data generation | W3-W6 | Faker generators, Bronze backfill | TODO |
| 3. Quality & transform | W6-W8 | Great Expectations, dbt Silver+Gold | TODO |
| 4. Dashboard MVP | W9-W10 | FastAPI + dashboard, 7 sections | TODO |
| 5. ML | W11-W15 | Reactivation, recsys, A/B engine | TODO |
| 6. RAG + NLI | W16-W18 | RAG insights + NLI verified citations | TODO |
| 7. Observability & launch | W19-W22 | Drift detection, polish, launch | TODO |

### Quick start (Windows + PowerShell)

```powershell
git clone https://github.com/YOUR_USERNAME/retaillens.git
cd retaillens

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

copy .env.example .env
# Open .env, fill in SUPABASE_URL / SUPABASE_SERVICE_KEY / SUPABASE_BUCKET

cd pipeline
python 00_health_check.py
```

A passing health check (exit 0) means the environment is ready for Phase 2.

### License

MIT
