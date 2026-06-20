"""
pipeline/export_to_bq.py
========================
Push all 5 Gold marts from local DuckDB → BigQuery.
Run this after every `dbt run` to keep BQ in sync.

Usage (PowerShell):
  cd C:\\Users\\Admin\\Documents\\e-commerce
  python pipeline/export_to_bq.py

What it does:
  1. Connects to local DuckDB (reads Gold schema)
  2. For each mart: reads as Arrow table (zero-copy, fast)
  3. Uploads to BigQuery via load_table_from_dataframe (WRITE_TRUNCATE)
  4. Prints row counts and BQ table URLs

Env vars needed (.env):
  DUCKDB_PATH                   path to ecom.duckdb
  GCP_PROJECT_ID                your GCP project id
  GOOGLE_APPLICATION_CREDENTIALS path to service-account JSON key
  BQ_DATASET                    BigQuery dataset name (default: ecom_gold)
  BQ_LOCATION                   BigQuery location (default: US)
"""

import os
import sys
import time
import duckdb
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────
DB_PATH    = Path(os.getenv("DUCKDB_PATH", "data/ecom.duckdb"))
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
KEY_FILE   = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials/gcp-key.json")
DATASET    = os.getenv("BQ_DATASET", "ecom_gold")
LOCATION   = os.getenv("BQ_LOCATION", "US")

GOLD_MARTS = [
    "mart_logistics_sla",
    "mart_customer_360",
    "mart_sales_and_demand",
    "mart_product_affinity",
    "mart_voice_of_customer",
]

# ── Helpers ─────────────────────────────────────────────────────────────────
def get_bq_client() -> bigquery.Client:
    if not PROJECT_ID:
        print("❌  GCP_PROJECT_ID not set in .env")
        sys.exit(1)
    key_path = Path(KEY_FILE)
    if not key_path.exists():
        print(f"❌  GCP key file not found: {key_path.resolve()}")
        print("    Create a service account key at:")
        print("    console.cloud.google.com → IAM → Service Accounts → Keys")
        sys.exit(1)
    creds = service_account.Credentials.from_service_account_file(
        str(key_path),
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return bigquery.Client(project=PROJECT_ID, credentials=creds)


def ensure_dataset(client: bigquery.Client) -> None:
    dataset_ref = f"{PROJECT_ID}.{DATASET}"
    try:
        client.get_dataset(dataset_ref)
        print(f"  Dataset {dataset_ref} exists ✓")
    except Exception:
        ds = bigquery.Dataset(dataset_ref)
        ds.location = LOCATION
        client.create_dataset(ds)
        print(f"  Created dataset {dataset_ref} ✓")


def export_mart(
    con: duckdb.DuckDBPyConnection,
    client: bigquery.Client,
    mart: str,
) -> dict:
    """Read one Gold mart from DuckDB, push to BigQuery."""
    t0 = time.time()

    # Read from DuckDB gold schema
    df: pd.DataFrame = con.execute(f"SELECT * FROM main_gold.{mart}").df()

    # BigQuery doesn't like pandas Timestamp with timezone in some versions
    for col in df.select_dtypes(include=["datetimetz"]).columns:
        df[col] = df[col].dt.tz_localize(None)

    table_id = f"{PROJECT_ID}.{DATASET}.{mart}"
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )

    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()  # wait

    elapsed = time.time() - t0
    return {
        "mart": mart,
        "rows": len(df),
        "cols": len(df.columns),
        "elapsed_s": round(elapsed, 1),
        "bq_url": f"https://console.cloud.google.com/bigquery?project={PROJECT_ID}&ws=!1m5!1m4!4m3!1s{PROJECT_ID}!2s{DATASET}!3s{mart}",
    }


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*65}")
    print(f"  E-Commerce Intelligence Platform — DuckDB → BigQuery Export")
    print(f"  Project  : {PROJECT_ID}")
    print(f"  Dataset  : {DATASET}")
    print(f"  DuckDB   : {DB_PATH.resolve()}")
    print(f"{'='*65}\n")

    if not DB_PATH.exists():
        print(f"❌  DuckDB file not found: {DB_PATH.resolve()}")
        print("    Run pipeline/ingest_bronze.py and dbt run first.")
        sys.exit(1)

    client = get_bq_client()
    ensure_dataset(client)
    print()

    results = []
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        for mart in GOLD_MARTS:
            print(f"  Exporting {mart} ...", end=" ", flush=True)
            try:
                r = export_mart(con, client, mart)
                print(f"{r['rows']:>8,} rows  {r['elapsed_s']}s  ✓")
                results.append(r)
            except Exception as e:
                print(f"  ❌  FAILED: {e}")
                results.append({"mart": mart, "rows": 0, "elapsed_s": 0, "error": str(e)})

    # Summary
    total_rows = sum(r.get("rows", 0) for r in results)
    ok_count   = sum(1 for r in results if "error" not in r)

    print(f"\n{'─'*65}")
    print(f"  ✅  {ok_count}/{len(GOLD_MARTS)} marts exported  ·  {total_rows:,} total rows")
    print(f"\n  BigQuery console:")
    print(f"  https://console.cloud.google.com/bigquery?project={PROJECT_ID}\n")
    print(f"  Looker Studio data source:")
    print(f"  studio.data.google.com → Create → BigQuery → {PROJECT_ID} → {DATASET}\n")

    if ok_count < len(GOLD_MARTS):
        sys.exit(1)


if __name__ == "__main__":
    main()