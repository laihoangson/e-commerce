"""
pipeline/utils/storage_pipeline.py - DuckDB + Parquet sync with Supabase Storage.

The DuckDB file is the "lakehouse-in-a-file": it persists on Supabase Storage
between cron runs. At the start of each pipeline, we download it. At the end,
we upload it back. This module handles both directions.

Also handles syncing the Olist Parquet files (one-time uploaded via
scripts/setup_olist_parquet.py, then downloaded by ingestion).

Functions:
    download_duckdb()              - pull retaillens.duckdb from Storage
    upload_duckdb()                - push retaillens.duckdb to Storage
    download_olist_parquets()      - pull all Olist parquets to local dir
"""
from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

from pipeline.utils.supabase_client import get_client

# Convention: DuckDB file lives at this path locally
LOCAL_DUCKDB = Path("data/retaillens.duckdb")

# On Supabase Storage, this is the key (filename in bucket root)
REMOTE_DUCKDB = "retaillens.duckdb"

# Olist Parquet files prefix
OLIST_PREFIX = "olist/"
LOCAL_OLIST_DIR = Path("data/raw/olist")

# 9 Olist Parquet files we expect
OLIST_PARQUETS = [
    "olist_customers_dataset.parquet",
    "olist_geolocation_dataset.parquet",
    "olist_order_items_dataset.parquet",
    "olist_order_payments_dataset.parquet",
    "olist_order_reviews_dataset.parquet",
    "olist_orders_dataset.parquet",
    "olist_products_dataset.parquet",
    "olist_sellers_dataset.parquet",
    "product_category_name_translation.parquet",
]


def _bucket() -> str:
    return os.environ.get("SUPABASE_STORAGE_BUCKET", "retaillens-artifacts")


def download_duckdb(local_path: Path = LOCAL_DUCKDB) -> bool:
    """
    Download retaillens.duckdb from Supabase Storage to local path.

    Returns True if downloaded, False if file doesn't exist on Storage yet
    (which is OK on first run - DuckDB will be created fresh).
    """
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)

    client = get_client()
    bucket = _bucket()

    try:
        # Check if file exists first
        files = client.storage.from_(bucket).list("")
        existing = {f["name"] for f in files}
        if REMOTE_DUCKDB not in existing:
            logger.info(f"No remote DuckDB found at {bucket}/{REMOTE_DUCKDB} (first run?)")
            return False

        data = client.storage.from_(bucket).download(REMOTE_DUCKDB)
        local_path.write_bytes(data)
        size_mb = len(data) / 1024 / 1024
        logger.success(
            f"Downloaded {bucket}/{REMOTE_DUCKDB} -> {local_path} ({size_mb:.1f} MB)"
        )
        return True

    except Exception as e:
        logger.warning(f"Could not download DuckDB: {e}. Will start fresh.")
        return False


def upload_duckdb(local_path: Path = LOCAL_DUCKDB) -> None:
    """Upload local DuckDB file back to Supabase Storage. Overwrites remote."""
    local_path = Path(local_path)
    if not local_path.exists():
        raise FileNotFoundError(f"DuckDB file not found at {local_path}")

    client = get_client()
    bucket = _bucket()

    with open(local_path, "rb") as f:
        client.storage.from_(bucket).upload(
            path=REMOTE_DUCKDB,
            file=f,
            file_options={
                "content-type": "application/octet-stream",
                "upsert": "true",
            },
        )

    size_mb = local_path.stat().st_size / 1024 / 1024
    logger.success(
        f"Uploaded {local_path} -> {bucket}/{REMOTE_DUCKDB} ({size_mb:.1f} MB)"
    )


def download_olist_parquets(local_dir: Path = LOCAL_OLIST_DIR) -> list[Path]:
    """
    Download all Olist Parquet files from Supabase Storage to local_dir.

    Returns list of local Paths to downloaded files.
    Raises if any expected file is missing on Storage (bootstrap not done).
    """
    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    client = get_client()
    bucket = _bucket()

    # List files in olist/ prefix
    files = client.storage.from_(bucket).list(OLIST_PREFIX.rstrip("/"))
    existing = {f["name"] for f in files}

    missing = [p for p in OLIST_PARQUETS if p not in existing]
    if missing:
        raise FileNotFoundError(
            f"Olist Parquets not on Storage: {missing}. "
            f"Run `python scripts/setup_olist_parquet.py` first."
        )

    local_paths = []
    for parquet_name in OLIST_PARQUETS:
        remote = f"{OLIST_PREFIX}{parquet_name}"
        local = local_dir / parquet_name
        data = client.storage.from_(bucket).download(remote)
        local.write_bytes(data)
        local_paths.append(local)

    total_mb = sum(p.stat().st_size for p in local_paths) / 1024 / 1024
    logger.success(
        f"Downloaded {len(local_paths)} Olist Parquets to {local_dir} "
        f"(total {total_mb:.1f} MB)"
    )
    return local_paths


if __name__ == "__main__":
    # Quick smoke test
    import argparse
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--action",
        choices=["download-duckdb", "upload-duckdb", "download-olist"],
        required=True,
    )
    args = parser.parse_args()

    if args.action == "download-duckdb":
        download_duckdb()
    elif args.action == "upload-duckdb":
        upload_duckdb()
    elif args.action == "download-olist":
        download_olist_parquets()