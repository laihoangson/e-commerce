## RetailLens

Solo end-to-end e-commerce intelligence platform built as a portfolio project. Demonstrates a generalist DE/DA/DS/MLE skill set across the full data lifecycle, running entirely on $0 free-tier cloud services.

> "See your business through the right lens."

### Data approach

The platform uses a hybrid dataset: the real Olist Brazilian e-commerce dataset (~99k orders, Sept 2016 to Oct 2018) as the historical core, plus a small synthetic live tail (2024-2026) that continues the timeline. The live tail is documented synthetic data, generated to keep the dashboard current and to host controlled A/B experiments. All monetary values are in Brazilian Real (BRL).

- Historical core: real Olist transactions loaded into Bronze
- Live tail: ~20 synthetic orders/day (2024-2026), reusing real Olist product/seller/customer pools
- Live tail encodes a disclosed, noisy loyalty pattern so the reactivation model has genuine signal to learn

### Architecture - Medallion (Bronze -> Silver -> Gold)

- Bronze: 9 raw synthetic tables as DuckDB native TABLEs, each carrying 4 metadata columns (_ingested_at, _source_file, _batch_id, _is_valid)
- Silver: cleansed star schema via dbt - 6 dimensions + 4 facts
- Gold: business marts synced to Supabase Postgres

### Tech stack ($0 free tier)

DuckDB (warehouse) · Supabase Storage + Postgres · dbt · Great Expectations · GitHub Actions · FastAPI on Render · vanilla JS on GitHub Pages · Groq · ChromaDB · UptimeRobot + Slack.

### Status

In active development.

| Phase | Weeks | Milestone | Status |
|-------|-------|-----------|--------|
| 1. Foundation | W1-W2 | Repo, GHA, Supabase, health check | Done |
| 2. Data ingestion | W3-W6 | Olist load + synthetic live tail | Done |
| 3. Quality & transform | W6-W8 | Great Expectations, dbt Silver+Gold | Done |
| 4. Dashboard | W9-W10 | FastAPI + 2-tab dashboard, map, 13 sections | Done |
| 5. ML | W11-W15 | Reactivation, recsys, A/B (notebook done) | In progress |
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
