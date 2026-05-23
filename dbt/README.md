## dbt — RetailLens Silver + Gold

Transforms validated Bronze into a Silver star schema (6 dimensions + 4 facts)
and Gold business marts.

### Prerequisites

Bronze must be ingested and validated first (so `_is_valid` is set):

```powershell
python pipeline/01_ingest_bronze.py --mode backfill
python pipeline/02_validate_bronze.py
```

### Run

From the `dbt/` directory:

```powershell
cd dbt
dbt run --profiles-dir .
```

The DuckDB path is read from the `DUCKDB_PATH` env var (defaults to
`../data/retaillens.duckdb`). Models are written to the `main_silver` and
`main_gold` schemas in the same DuckDB file.

### Models

Silver: dim_customers, dim_products, dim_sellers, dim_date, dim_geography,
dim_payment_type, fact_orders, fact_order_items, fact_payments, fact_reviews.

Gold: daily_revenue, customer_ltv (RFM), cohort_retention, seller_metrics,
ab_test_results, funnel_conversion.

Silver models filter `_is_valid = true`; Bronze retains all raw rows.
