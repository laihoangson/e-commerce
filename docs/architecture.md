# Architecture

> Last updated: Week 1. Major revisions at W4 and W16.

## Three views

This document follows a C4-style breakdown: context → container → deployment.

### 1. System context

Six stakeholder personas consume the dashboard: Mai/CEO, Hùng/Marketing, Linh/Ops, Tú/Product, An/CRM, Phương/Risk. Pipeline operator monitors via Slack + GitHub Actions logs.

External systems:
- Olist Kaggle dataset — 99k orders, 9 tables, source of truth for historical data
- Faker generator — synthetic clickstream, marketing events, inventory updates
- Groq API — LLM inference for RAG insights
- Supabase — Postgres + Storage for state persistence
- Render — FastAPI host for ML serving

### 2. Container view

Data flows top-to-bottom through 4 layers:

1. Ingestion — Olist CSVs + Faker synthetic events land in Bronze
2. Bronze — Raw rows preserved with metadata + `_is_valid` flag
3. Silver — Cleaned, conformed, star schema with SCD2 product snapshots
4. Gold — 9 business marts aggregated for dashboard consumption

Three downstream consumers fan out from Gold:
- ML serving — FastAPI with churn + fraud models
- RAG engine — ChromaDB + Groq for auto-generated insights
- AB engine — Statistical tests for experiments

All three feed the dashboard (6 sections).

### 3. Deployment topology

Three deployment environments connected by API + file transfer:

- GitHub Actions runner — Ephemeral, cron 6h. Downloads DuckDB from Storage, transforms, uploads back.
- Supabase — Persistent state. Storage holds DuckDB + ChromaDB tarball. Postgres holds Gold tables exposed via REST.
- Render — Long-lived FastAPI serving ML predictions. UptimeRobot pings every 5 min to prevent cold starts.
- GitHub Pages — Static dashboard, no backend, reads Supabase REST directly.

## Key design decisions

### DD-1: DuckDB as "lakehouse-in-a-file"

Decision: A single `retaillens.duckdb` file lives on Supabase Storage between pipeline runs.

Why: Cost ($0 vs $50+/mo for managed warehouse), OLAP performance for 99k orders, portable (anyone can clone and analyze locally).

Trade-offs: Not suitable for concurrent writes; cannot scale beyond ~10GB. Acceptable for this dataset and use case. Migration path documented in `streaming-extension.md`.

### DD-2: Bronze preserves raw + flag, Silver filters

Decision: Invalid rows (failed Great Expectations checks) stay in Bronze with `_is_valid = FALSE`. Silver filters them out.

Why: Auditable, replayable, standard pattern in modern data engineering.

### DD-3: Two-mode synthetic data

- Backfill — Generates 2016-2018 data aligned with Olist timestamps. Run once during W3.
- Live — Generates 2026 events for a random subset of Olist customer_ids. Runs every cron.

Why: Backfill makes history queries meaningful; live makes the dashboard feel alive between runs.

### DD-4: ChromaDB persisted as tarball

Decision: Tar the entire `chromadb_persist/` folder, upload as a single `.tar.gz` to Supabase Storage.

Why: One upload + one download per cron run (vs hundreds of small files). Atomic snapshots.

### DD-5: Streaming extension is local-only

Decision: `streaming_simulator/` contains docker-compose with Kafka + Spark + migration-path docs. Never deployed.

Why: Real streaming infrastructure breaks the $0 promise. The point is to demonstrate design capability, not operate streaming in production.

What recruiters see:
- `kafka_producer.py` replays Olist orders with 1000x speedup
- `spark_consumer_stub.py` writes to DuckDB Bronze with same schema
- `docs/streaming-extension.md` explains migration when scale demands it