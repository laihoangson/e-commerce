r"""
pipeline/ingest_bronze.py
=========================
Load all 9 Olist CSVs into DuckDB as Bronze tables.

Expected CSV layout (in OLIST_CSV_DIR):
  olist_customers_dataset.csv
  olist_geolocation_dataset.csv
  olist_order_items_dataset.csv
  olist_order_payments_dataset.csv
  olist_order_reviews_dataset.csv
  olist_orders_dataset.csv
  olist_products_dataset.csv
  olist_sellers_dataset.csv
  product_category_name_translation.csv

Usage (PowerShell):
  cd C:\Users\Admin\Documents\e-commerce
  python pipeline/ingest_bronze.py

Env vars needed (.env):
  OLIST_CSV_DIR   - path to folder containing the 9 CSVs
  DUCKDB_PATH     - path to .duckdb file (created if missing)
"""

import os
import sys
import duckdb
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
CSV_DIR   = Path(os.getenv("OLIST_CSV_DIR", "data/raw/olist"))
DB_PATH   = Path(os.getenv("DUCKDB_PATH",   "data/ecom.duckdb"))
BATCH_ID  = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

# Map: DuckDB table name → CSV filename
TABLES = {
    "bronze_customers":    "olist_customers_dataset.csv",
    "bronze_geolocation":  "olist_geolocation_dataset.csv",
    "bronze_order_items":  "olist_order_items_dataset.csv",
    "bronze_payments":     "olist_order_payments_dataset.csv",
    "bronze_reviews":      "olist_order_reviews_dataset.csv",
    "bronze_orders":       "olist_orders_dataset.csv",
    "bronze_products":     "olist_products_dataset.csv",
    "bronze_sellers":      "olist_sellers_dataset.csv",
    "bronze_category_xlat":"product_category_name_translation.csv",
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def validate_csvs() -> list[str]:
    """Return list of missing CSV files."""
    missing = []
    for table, fname in TABLES.items():
        if not (CSV_DIR / fname).exists():
            missing.append(fname)
    return missing


def ingest_table(con: duckdb.DuckDBPyConnection, table: str, csv_path: Path) -> dict:
    """
    Load one CSV into DuckDB with 4 metadata columns:
      _ingested_at  TIMESTAMPTZ — when this row was loaded
      _source_file  VARCHAR     — original CSV filename
      _batch_id     VARCHAR     — ISO timestamp of this run
      _is_valid     BOOLEAN     — placeholder for GE validation (default TRUE)
    Returns dict with row count and status.
    """
    df = pd.read_csv(csv_path, low_memory=False)
    now = datetime.now(timezone.utc)

    df["_ingested_at"] = now
    df["_source_file"] = csv_path.name
    df["_batch_id"]    = BATCH_ID
    df["_is_valid"]    = True

    # Drop existing table (full-reload on each run)
    con.execute(f"DROP TABLE IF EXISTS {table}")
    con.execute(f"CREATE TABLE {table} AS SELECT * FROM df")

    row_count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return {"table": table, "rows": row_count, "status": "ok"}


def dedup_geolocation(con: duckdb.DuckDBPyConnection) -> None:
    """
    Geolocation CSV has ~1M rows but only ~19k unique zip prefixes.
    Deduplicate to one row per zip_code_prefix keeping AVG lat/lng.
    Replaces bronze_geolocation in-place.
    """
    con.execute("""
        CREATE OR REPLACE TABLE bronze_geolocation AS
        SELECT
            geolocation_zip_code_prefix,
            AVG(geolocation_lat)  AS geolocation_lat,
            AVG(geolocation_lng)  AS geolocation_lng,
            FIRST(geolocation_city)  AS geolocation_city,
            FIRST(geolocation_state) AS geolocation_state,
            MAX(_ingested_at)  AS _ingested_at,
            FIRST(_source_file) AS _source_file,
            FIRST(_batch_id)    AS _batch_id,
            TRUE                AS _is_valid
        FROM bronze_geolocation
        GROUP BY geolocation_zip_code_prefix
    """)
    new_count = con.execute("SELECT COUNT(*) FROM bronze_geolocation").fetchone()[0]
    print(f"  [geo] deduped → {new_count:,} unique zip prefixes")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*60}")
    print(f"  E-Commerce Intelligence Platform — Bronze Ingestion")
    print(f"  Batch: {BATCH_ID}")
    print(f"  Source dir: {CSV_DIR.resolve()}")
    print(f"  DuckDB: {DB_PATH.resolve()}")
    print(f"{'='*60}\n")

    # Pre-flight checks
    missing = validate_csvs()
    if missing:
        print("❌  Missing CSV files:")
        for f in missing:
            print(f"     {CSV_DIR / f}")
        print("\n  Download from Kaggle:")
        print("  https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce")
        sys.exit(1)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    results = []
    with duckdb.connect(str(DB_PATH)) as con:
        for table, fname in TABLES.items():
            csv_path = CSV_DIR / fname
            print(f"  Loading {fname} ...", end=" ", flush=True)
            r = ingest_table(con, table, csv_path)
            print(f"{r['rows']:>8,} rows  ✓")
            results.append(r)

        # Post-load: deduplicate geolocation
        print(f"\n  Post-processing geolocation ...")
        dedup_geolocation(con)

        # Summary stats
        total = sum(r["rows"] for r in results if r["table"] != "bronze_geolocation")
        orders = con.execute("SELECT COUNT(*) FROM bronze_orders").fetchone()[0]
        print(f"\n{'─'*60}")
        print(f"  ✅  Bronze ingestion complete")
        print(f"  Total rows loaded : {sum(r['rows'] for r in results):>10,}")
        print(f"  Orders            : {orders:>10,}")
        print(f"  Tables created    : {len(results)}")
        print(f"  DuckDB size       : {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")
        print(f"{'='*60}\n")

        # Quick validation
        print("  Quick checks:")
        checks = [
            ("Orders with customer", "SELECT COUNT(*) FROM bronze_orders o JOIN bronze_customers c ON o.customer_id = c.customer_id"),
            ("Items with order",     "SELECT COUNT(*) FROM bronze_order_items i JOIN bronze_orders o ON i.order_id = o.order_id"),
            ("Reviews with order",   "SELECT COUNT(*) FROM bronze_reviews r JOIN bronze_orders o ON r.order_id = o.order_id"),
        ]
        all_pass = True
        for label, sql in checks:
            count = con.execute(sql).fetchone()[0]
            status = "✓" if count > 0 else "✗"
            if count == 0:
                all_pass = False
            print(f"  {status}  {label}: {count:,}")

        if all_pass:
            print(f"\n  ✅  All FK checks passed. Run dbt next:\n")
            print(f"     cd dbt && dbt run\n")
        else:
            print(f"\n  ⚠️   Some FK checks failed — inspect CSV files.")
            sys.exit(1)


if __name__ == "__main__":
    main()