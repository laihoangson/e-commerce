"""Bronze ingestion orchestrator.

Generates customers + transactional tables and appends them to Bronze. Two modes:

  backfill : generate a historical window (default 2024-01-01 .. 2026-05-30)
  live     : generate only today's orders (used by the 12h cron during 2026)

Master tables must already exist (run scripts/generate_masters_once.py first).

Usage:
    python pipeline/01_ingest_bronze.py --mode backfill
    python pipeline/01_ingest_bronze.py --mode backfill --days 30   # quick test
    python pipeline/01_ingest_bronze.py --mode live
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import date, datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

from utils.bronze_writer import write_bronze  # noqa: E402
from utils.customer_generator import generate_customers  # noqa: E402
from utils.duckdb_client import ensure_schemas, get_connection, table_exists  # noqa: E402
from utils.order_generator import generate_transactional  # noqa: E402

DEFAULT_START = "2024-01-01"
DEFAULT_END = "2026-05-30"
BASE_PER_DAY = 100
SEED = 7

MASTER_TABLES = ("raw_geolocation", "raw_category_translation", "raw_sellers", "raw_products")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="RetailLens Bronze ingestion")
    p.add_argument("--mode", choices=["backfill", "live"], default="backfill")
    p.add_argument("--start-date", default=DEFAULT_START, help="backfill start (YYYY-MM-DD)")
    p.add_argument("--end-date", default=DEFAULT_END, help="backfill end (YYYY-MM-DD)")
    p.add_argument(
        "--days",
        type=int,
        default=None,
        help="if set, override window to the last N days ending at end-date (quick test)",
    )
    p.add_argument("--base-per-day", type=int, default=BASE_PER_DAY)
    return p.parse_args()


def _resolve_window(args: argparse.Namespace) -> tuple[str, str]:
    """Resolve the (start, end) date strings based on mode and flags."""
    if args.mode == "live":
        today = date.today().isoformat()
        return today, today
    if args.days is not None:
        end = datetime.fromisoformat(args.end_date).date()
        start = end - timedelta(days=args.days - 1)
        return start.isoformat(), end.isoformat()
    return args.start_date, args.end_date


def main() -> int:
    args = _parse_args()
    start, end = _resolve_window(args)
    batch_id = str(uuid.uuid4())

    print("=" * 56)
    print(f"RetailLens Bronze ingestion — mode={args.mode}")
    print(f"window: {start} .. {end}   batch: {batch_id[:8]}")
    print("=" * 56)

    con = get_connection()
    ensure_schemas(con)

    # Masters must exist first.
    missing = [t for t in MASTER_TABLES if not table_exists(con, "bronze", t)]
    if missing:
        print(f"[FAIL] missing master tables: {missing}")
        print("Run: python scripts/generate_masters_once.py")
        con.close()
        return 1

    geo = con.execute("SELECT * FROM bronze.raw_geolocation").df()
    products = con.execute("SELECT * FROM bronze.raw_products").df()
    sellers = con.execute("SELECT * FROM bronze.raw_sellers").df()

    # Estimate order count to size the customer pool (transactional generator
    # drives the true count; we slightly over-provision customers).
    n_days = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days + 1
    est_orders = int(n_days * args.base_per_day * 1.2)

    print(f"Generating ~{est_orders} customers ...")
    customers = generate_customers(est_orders, geo, seed=SEED)

    print("Generating transactional tables ...")
    tx = generate_transactional(
        customers,
        products,
        sellers,
        start_date=start,
        end_date=end,
        base_per_day=args.base_per_day,
        seed=SEED,
    )

    # Align the customers table to the actual orders produced.
    n_orders = len(tx["raw_orders"])
    customers_final = customers.iloc[:n_orders].reset_index(drop=True)

    # Write everything. Backfill replaces; live appends.
    replace = args.mode == "backfill"
    write_bronze(
        con, customers_final, "raw_customers", "customer_generator", batch_id, replace=replace
    )
    print(f"  [OK] bronze.raw_customers: {len(customers_final)} rows")

    for table, df in tx.items():
        n = write_bronze(con, df, table, "order_generator", batch_id, replace=replace)
        print(f"  [OK] bronze.{table}: {n} rows")

    con.close()
    print("Bronze ingestion complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
