"""Inspect Bronze tables: row counts, sample rows, and FK integrity checks.

Usage:
    python scripts/inspect_bronze.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from dotenv import load_dotenv  # noqa: E402

from utils.duckdb_client import get_connection, table_exists  # noqa: E402

load_dotenv()

TABLES = [
    "raw_geolocation",
    "raw_category_translation",
    "raw_sellers",
    "raw_products",
    "raw_customers",
    "raw_orders",
    "raw_order_items",
    "raw_payments",
    "raw_reviews",
]


def main() -> int:
    con = get_connection()

    print("Row counts:")
    for t in TABLES:
        if table_exists(con, "bronze", t):
            n = con.execute(f"SELECT count(*) FROM bronze.{t}").fetchone()[0]
            print(f"  bronze.{t}: {n}")
        else:
            print(f"  bronze.{t}: (missing)")

    print("\nFK integrity (orphans should be 0):")
    checks = {
        "order_items.order_id -> orders": (
            "SELECT count(*) FROM bronze.raw_order_items i "
            "LEFT JOIN bronze.raw_orders o USING(order_id) WHERE o.order_id IS NULL"
        ),
        "payments.order_id -> orders": (
            "SELECT count(*) FROM bronze.raw_payments p "
            "LEFT JOIN bronze.raw_orders o USING(order_id) WHERE o.order_id IS NULL"
        ),
        "reviews.order_id -> orders": (
            "SELECT count(*) FROM bronze.raw_reviews r "
            "LEFT JOIN bronze.raw_orders o USING(order_id) WHERE o.order_id IS NULL"
        ),
        "orders.customer_id -> customers": (
            "SELECT count(*) FROM bronze.raw_orders o "
            "LEFT JOIN bronze.raw_customers c USING(customer_id) WHERE c.customer_id IS NULL"
        ),
        "order_items.product_id -> products": (
            "SELECT count(*) FROM bronze.raw_order_items i "
            "LEFT JOIN bronze.raw_products p USING(product_id) WHERE p.product_id IS NULL"
        ),
    }
    for label, sql in checks.items():
        try:
            n = con.execute(sql).fetchone()[0]
            flag = "OK" if n == 0 else "ORPHANS"
            print(f"  [{flag}] {label}: {n}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [SKIP] {label}: {exc}")

    print("\nReview score distribution:")
    try:
        rows = con.execute(
            "SELECT review_score, count(*) FROM bronze.raw_reviews "
            "GROUP BY review_score ORDER BY review_score"
        ).fetchall()
        total = sum(r[1] for r in rows) or 1
        for score, n in rows:
            print(f"  {score} stars: {n} ({100*n/total:.1f}%)")
    except Exception as exc:  # noqa: BLE001
        print(f"  (skip: {exc})")

    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
