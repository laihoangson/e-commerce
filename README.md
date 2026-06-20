# E-Commerce Intelligence Platform

End-to-end solo e-commerce intelligence platform. Demonstrates generalist DE / DA / DS / MLE skills on a $0 free-tier stack using the real Olist Brazilian marketplace dataset (~100k orders).

> Supply chain intelligence, demand forecasting, customer segmentation, NLP sentiment, and cross-sell recommendations — all in one pipeline.

[![Python](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![dbt](https://img.shields.io/badge/dbt-1.8-orange)](https://getdbt.com)
[![DuckDB](https://img.shields.io/badge/DuckDB-0.10-yellow)](https://duckdb.org)

## Architecture

```
Olist CSVs (Bronze)
    └─► DuckDB (ingest_bronze.py)
            └─► dbt Silver (3 models: stg_orders, stg_order_items, stg_reviews)
                    └─► dbt Gold (5 marts)
                            ├─ mart_logistics_sla       → historical.html
                            ├─ mart_sales_and_demand    → historical.html + Prophet
                            ├─ mart_customer_360        → K-Means segmentation
                            ├─ mart_product_affinity    → Apriori cross-sell
                            └─ mart_voice_of_customer   → DistilBERT sentiment
```

## Stack

| Layer | Tech | Cost |
|-------|------|------|
| Warehouse | DuckDB | $0 |
| Transform | dbt-core + dbt-duckdb | $0 |
| Storage | Supabase (free tier) | $0 |
| API | FastAPI on Render | $0 |
| Dashboard | GitHub Pages | $0 |
| LLM | Groq API (free tier) | $0 |

## Quick Start (Windows / PowerShell)

```powershell
git clone https://github.com/laihoangson/e-commerce.git
cd e-commerce

# 1. Place Olist CSVs in data/raw/olist/
#    Download: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

# 2. Setup + ingest Bronze
.\scripts\setup.ps1

# 3. Run dbt transforms
cd dbt
dbt deps
dbt run
dbt test

# 4. Open dashboard
start frontend/historical.html
```

## Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1. Foundation | ✅ Done | Bronze ingestion, dbt Silver + Gold |
| 2. ML Training | 🔵 Next | XGBoost, Prophet, K-Means, DistilBERT, Apriori |
| 3. Live AI Portal | ⏳ Planned | FastAPI on Render, live.html command center |
| 4. Engineering Docs | ⏳ Planned | Medallion diagram, scale-up roadmap |

## Data

**Olist Brazilian E-Commerce** — 99,441 real orders, Sep 2016 – Oct 2018.  
License: CC BY-NC-SA 4.0 · Source: Kaggle  
9 CSVs: orders, customers, sellers, products, reviews, payments, geolocation, order_items, category_translation.
