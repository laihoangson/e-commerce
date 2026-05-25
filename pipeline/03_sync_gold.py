"""Sync Gold marts from DuckDB to Supabase Postgres.

Reads each Gold mart from the DuckDB main_gold schema and writes it to a public
table in Supabase Postgres (replace mode), so Supabase's REST API can serve it.

Run after dbt build:
    python pipeline/03_sync_gold.py
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

load_dotenv()

from utils.duckdb_client import get_connection, table_exists  # noqa: E402
from utils.postgres_client import check_connection, get_engine  # noqa: E402

GOLD_MARTS = [
    "daily_revenue",
    "customer_ltv",
    "cohort_retention",
    "seller_metrics",
    "ab_test_results",
    "funnel_conversion",
    "delivery_performance",
    "review_analysis",
    "revenue_by_state",
]

# dbt writes Gold to the main_gold schema in DuckDB.
DUCKDB_GOLD_SCHEMA = "main_gold"


def main() -> int:
    print("=" * 56)
    print("RetailLens — Sync Gold to Supabase Postgres")
    print("=" * 56)

    con = get_connection()

    try:
        engine = get_engine()
    except RuntimeError as exc:
        print(f"[FAIL] {exc}")
        con.close()
        return 1

    if not check_connection(engine):
        print("[FAIL] could not connect to Supabase Postgres. Check SUPABASE_DB_URL.")
        con.close()
        return 1
    print("[OK] connected to Supabase Postgres")

    synced = 0
    for mart in GOLD_MARTS:
        if not table_exists(con, DUCKDB_GOLD_SCHEMA, mart):
            print(f"  [SKIP] {mart}: not found in {DUCKDB_GOLD_SCHEMA} (run dbt first?)")
            continue
        df = con.execute(f"SELECT * FROM {DUCKDB_GOLD_SCHEMA}.{mart}").df()
        # Write to public schema; replace so re-runs are idempotent.
        df.to_sql(mart, engine, schema="public", if_exists="replace", index=False)
        print(f"  [OK] {mart}: {len(df)} rows -> public.{mart}")
        synced += 1

    con.close()
    print("=" * 56)
    print(f"Synced {synced}/{len(GOLD_MARTS)} marts.")
    print("Supabase REST API now serves these at /rest/v1/<mart>.")
    return 0 if synced > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
