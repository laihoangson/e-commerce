"""
scripts/setup_olist_parquet.py - One-time bootstrap.

Downloads Olist Brazilian E-commerce dataset from Kaggle, converts the 9 CSV
files to compressed Parquet, then uploads to Supabase Storage under prefix
'olist/'. After this runs once, the cron pipeline can pull Parquet files
from Supabase (faster + smaller than re-downloading from Kaggle every 6h).

Run locally:
    python scripts/setup_olist_parquet.py

Idempotent: skips upload if file already exists on Supabase Storage,
unless --force is passed.
"""
from __future__ import annotations

import argparse
import io
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv
from loguru import logger

# Make project root importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.utils.supabase_client import get_client  # noqa: E402

load_dotenv()


# Olist dataset on Kaggle
KAGGLE_DATASET = "olistbr/brazilian-ecommerce"

# 9 CSV files inside the Olist zip
OLIST_FILES = [
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
]

# Storage layout on Supabase
STORAGE_PREFIX = "olist/"


def download_olist_to_temp(tmpdir: Path) -> Path:
    """Download Olist via Kaggle CLI and unzip into tmpdir/csvs/."""
    logger.info(f"Downloading Olist from Kaggle to {tmpdir}")

    # Import inside function so missing kaggle CLI doesn't crash module import
    import kaggle

    kaggle.api.authenticate()
    kaggle.api.dataset_download_files(
        KAGGLE_DATASET,
        path=str(tmpdir),
        unzip=True,
        quiet=False,
    )

    csv_dir = tmpdir
    # Verify all 9 files present
    missing = [f for f in OLIST_FILES if not (csv_dir / f).exists()]
    if missing:
        raise FileNotFoundError(f"Olist download incomplete. Missing: {missing}")

    logger.success(f"All {len(OLIST_FILES)} Olist CSVs downloaded")
    return csv_dir


def csv_to_parquet(csv_path: Path, parquet_path: Path) -> int:
    """Convert one CSV to compressed Parquet. Returns row count."""
    df = pd.read_csv(csv_path)
    rows = len(df)

    # Use snappy compression - default Parquet codec, good speed/size trade-off
    df.to_parquet(parquet_path, compression="snappy", index=False)

    size_csv = csv_path.stat().st_size
    size_pq = parquet_path.stat().st_size
    ratio = size_csv / size_pq if size_pq else 0
    logger.info(
        f"{csv_path.name}: {rows:,} rows | "
        f"{size_csv/1024:.0f} KB CSV -> {size_pq/1024:.0f} KB Parquet "
        f"({ratio:.1f}x smaller)"
    )
    return rows


def upload_to_supabase(local_path: Path, remote_path: str, force: bool) -> None:
    """Upload Parquet file to Supabase Storage."""
    import os

    bucket = os.environ.get("SUPABASE_STORAGE_BUCKET", "retaillens-artifacts")
    client = get_client()

    # Check if already exists
    try:
        existing = client.storage.from_(bucket).list(STORAGE_PREFIX.rstrip("/"))
        existing_names = {f["name"] for f in existing}
        filename = Path(remote_path).name
        if filename in existing_names and not force:
            logger.info(f"Skipping {remote_path} (already exists, use --force to overwrite)")
            return
    except Exception as e:
        logger.warning(f"Could not list existing files: {e}")

    with open(local_path, "rb") as f:
        client.storage.from_(bucket).upload(
            path=remote_path,
            file=f,
            file_options={
                "content-type": "application/octet-stream",
                "upsert": "true",
            },
        )
    logger.success(f"Uploaded {bucket}/{remote_path} ({local_path.stat().st_size/1024:.0f} KB)")


def main(force: bool = False) -> int:
    logger.info("=== Olist -> Parquet -> Supabase Storage bootstrap ===")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        csv_dir = download_olist_to_temp(tmpdir)

        parquet_dir = tmpdir / "parquet"
        parquet_dir.mkdir()

        total_rows = 0
        for csv_name in OLIST_FILES:
            csv_path = csv_dir / csv_name
            parquet_name = csv_name.replace(".csv", ".parquet")
            parquet_path = parquet_dir / parquet_name

            rows = csv_to_parquet(csv_path, parquet_path)
            total_rows += rows

            remote = f"{STORAGE_PREFIX}{parquet_name}"
            upload_to_supabase(parquet_path, remote, force=force)

        logger.success(f"Bootstrap complete. Total rows uploaded: {total_rows:,}")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing Parquet files on Supabase Storage",
    )
    args = parser.parse_args()

    try:
        sys.exit(main(force=args.force))
    except Exception as e:
        logger.exception(f"Bootstrap failed: {e}")
        sys.exit(1)