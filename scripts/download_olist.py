"""Download the 9 Olist Brazilian e-commerce CSV files.

Source: the official Olist data repository on GitHub (no auth required),
mirroring the Kaggle "Brazilian E-Commerce Public Dataset by Olist".

Writes to data/raw/olist/.

Usage:
    python scripts/download_olist.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

BASE_URL = "https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets"
OUT_DIR = Path("data/raw/olist")

FILES = [
    "olist_customers_dataset",
    "olist_geolocation_dataset",
    "olist_order_items_dataset",
    "olist_order_payments_dataset",
    "olist_order_reviews_dataset",
    "olist_orders_dataset",
    "olist_products_dataset",
    "olist_sellers_dataset",
    "product_category_name_translation",
]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {len(FILES)} Olist files to {OUT_DIR} ...")

    for name in FILES:
        url = f"{BASE_URL}/{name}.csv"
        dest = OUT_DIR / f"{name}.csv"
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAIL] {name}: {exc}")
            return 1
        dest.write_bytes(resp.content)
        size_mb = len(resp.content) / 1e6
        print(f"  [OK] {name}.csv ({size_mb:.1f} MB)")

    print("All Olist files downloaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
