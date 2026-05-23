"""Load the 9 Olist CSV files into the Bronze layer.

Maps the real Olist schema onto the RetailLens Bronze tables. Olist is the
historical core (2016-2018); a small Faker generator later appends a live tail
(2018->2026) in a separate step.

Key mappings and cleaning:
  - zip_code_prefix -> postcode (kept as string)
  - geolocation deduplicated to one row per zip prefix
  - products: keep only the schema columns; drop Olist extras
  - orders: ab_experiment / ab_variant set NULL (real data has no experiment;
    the Faker live tail carries A/B)
  - a _data_source column ('olist') marks historical rows

Run after downloading:
    python pipeline/load_olist_bronze.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from utils.bronze_writer import write_bronze  # noqa: E402
from utils.duckdb_client import ensure_schemas, get_connection  # noqa: E402

OLIST_DIR = Path("data/raw/olist")
BATCH = f"olist-{uuid.uuid4().hex[:8]}"


def _read(name: str) -> pd.DataFrame:
    return pd.read_csv(OLIST_DIR / f"{name}.csv", dtype=str)


def load_geolocation() -> pd.DataFrame:
    df = _read("olist_geolocation_dataset")
    # Deduplicate to one row per zip prefix (Olist has ~1M rows, many dupes).
    df = df.drop_duplicates(subset=["geolocation_zip_code_prefix"]).copy()
    return pd.DataFrame(
        {
            "geolocation_postcode": df["geolocation_zip_code_prefix"],
            "geolocation_lat": pd.to_numeric(df["geolocation_lat"], errors="coerce"),
            "geolocation_lng": pd.to_numeric(df["geolocation_lng"], errors="coerce"),
            "geolocation_city": df["geolocation_city"],
            "geolocation_state": df["geolocation_state"],
        }
    )


def load_categories() -> pd.DataFrame:
    df = _read("product_category_name_translation")
    df.columns = [c.strip().lstrip("\ufeff") for c in df.columns]
    return df[["product_category_name", "product_category_name_english"]]


def load_sellers() -> pd.DataFrame:
    df = _read("olist_sellers_dataset")
    return pd.DataFrame(
        {
            "seller_id": df["seller_id"],
            "seller_postcode": df["seller_zip_code_prefix"],
            "seller_city": df["seller_city"],
            "seller_state": df["seller_state"],
        }
    )


def load_products() -> pd.DataFrame:
    df = _read("olist_products_dataset")
    num = lambda c: pd.to_numeric(df[c], errors="coerce")
    return pd.DataFrame(
        {
            "product_id": df["product_id"],
            "product_category_name": df["product_category_name"],
            "product_weight_g": num("product_weight_g"),
            "product_length_cm": num("product_length_cm"),
            "product_height_cm": num("product_height_cm"),
            "product_width_cm": num("product_width_cm"),
            # Olist has no base_price; derive a reference later if needed.
            "base_price": pd.NA,
        }
    )


def load_customers() -> pd.DataFrame:
    df = _read("olist_customers_dataset")
    return pd.DataFrame(
        {
            "customer_id": df["customer_id"],
            "customer_unique_id": df["customer_unique_id"],
            "customer_postcode": df["customer_zip_code_prefix"],
            "customer_city": df["customer_city"],
            "customer_state": df["customer_state"],
        }
    )


def load_orders() -> pd.DataFrame:
    df = _read("olist_orders_dataset")
    ts = lambda c: pd.to_datetime(df[c], errors="coerce")
    return pd.DataFrame(
        {
            "order_id": df["order_id"],
            "customer_id": df["customer_id"],
            "order_status": df["order_status"],
            "order_purchase_timestamp": ts("order_purchase_timestamp"),
            "order_approved_at": ts("order_approved_at"),
            "order_delivered_carrier_date": ts("order_delivered_carrier_date"),
            "order_delivered_customer_date": ts("order_delivered_customer_date"),
            "order_estimated_delivery_date": ts("order_estimated_delivery_date"),
            "ab_experiment": pd.NA,  # real data has no experiment
            "ab_variant": pd.NA,
        }
    )


def load_order_items() -> pd.DataFrame:
    df = _read("olist_order_items_dataset")
    return pd.DataFrame(
        {
            "order_id": df["order_id"],
            "order_item_id": pd.to_numeric(df["order_item_id"], errors="coerce"),
            "product_id": df["product_id"],
            "seller_id": df["seller_id"],
            "price": pd.to_numeric(df["price"], errors="coerce"),
            "freight_value": pd.to_numeric(df["freight_value"], errors="coerce"),
        }
    )


def load_payments() -> pd.DataFrame:
    df = _read("olist_order_payments_dataset")
    return pd.DataFrame(
        {
            "order_id": df["order_id"],
            "payment_sequential": pd.to_numeric(df["payment_sequential"], errors="coerce"),
            "payment_type": df["payment_type"],
            "payment_installments": pd.to_numeric(df["payment_installments"], errors="coerce"),
            "payment_value": pd.to_numeric(df["payment_value"], errors="coerce"),
        }
    )


def load_reviews() -> pd.DataFrame:
    df = _read("olist_order_reviews_dataset")
    return pd.DataFrame(
        {
            "review_id": df["review_id"],
            "order_id": df["order_id"],
            "review_score": pd.to_numeric(df["review_score"], errors="coerce"),
            "review_comment_title": df["review_comment_title"],
            "review_comment_message": df["review_comment_message"],
            "review_creation_date": pd.to_datetime(
                df["review_creation_date"], errors="coerce"
            ),
        }
    )


LOADERS = {
    "raw_geolocation": load_geolocation,
    "raw_category_translation": load_categories,
    "raw_sellers": load_sellers,
    "raw_products": load_products,
    "raw_customers": load_customers,
    "raw_orders": load_orders,
    "raw_order_items": load_order_items,
    "raw_payments": load_payments,
    "raw_reviews": load_reviews,
}


def main() -> int:
    if not OLIST_DIR.exists():
        print(f"[FAIL] {OLIST_DIR} not found. Run scripts/download_olist.py first.")
        return 1

    print("=" * 56)
    print(f"Loading Olist into Bronze (batch {BATCH})")
    print("=" * 56)

    con = get_connection()
    ensure_schemas(con)

    for table, loader in LOADERS.items():
        df = loader()
        # Tag historical source; replace mode (idempotent reload).
        df["_data_source"] = "olist"
        n = write_bronze(
            con, df, table, source_file="load_olist_bronze", batch_id=BATCH, replace=True
        )
        print(f"  [OK] bronze.{table}: {n} rows")

    con.close()
    print("Olist load complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
