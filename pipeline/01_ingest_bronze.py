"""
pipeline/01_ingest_bronze.py - Bronze layer ingestion.

Orchestrates:
    1. Download retaillens.duckdb from Supabase Storage (or start fresh)
    2. Download Olist Parquet files from Supabase Storage
    3. Load 7 Olist tables into bronze schema (idempotent: skip if loaded)
    4. Generate Faker clickstream events and append to bronze.raw_clickstream
    5. Upload updated DuckDB back to Supabase Storage

Run locally:
    python pipeline/01_ingest_bronze.py --mode backfill --num-events 50000
    python pipeline/01_ingest_bronze.py --mode live --num-events 2000

Run on GHA: see .github/workflows/pipeline.yml
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
from dotenv import load_dotenv
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.utils.duckdb_client import get_connection, init_db  # noqa: E402
from pipeline.utils.faker_generator import (  # noqa: E402
    generate_clickstream,
    write_to_duckdb as write_clickstream,
)
from pipeline.utils.storage_pipeline import (  # noqa: E402
    LOCAL_DUCKDB,
    LOCAL_OLIST_DIR,
    OLIST_PARQUETS,
    download_duckdb,
    download_olist_parquets,
    upload_duckdb,
)

load_dotenv()


# Mapping: Parquet filename -> bronze table name
OLIST_TABLE_MAP = {
    "olist_customers_dataset.parquet": "bronze.raw_customers",
    "olist_orders_dataset.parquet": "bronze.raw_orders",
    "olist_order_items_dataset.parquet": "bronze.raw_order_items",
    "olist_order_payments_dataset.parquet": "bronze.raw_payments",
    "olist_order_reviews_dataset.parquet": "bronze.raw_reviews",
    "olist_products_dataset.parquet": "bronze.raw_products",
    "olist_sellers_dataset.parquet": "bronze.raw_sellers",
    "olist_geolocation_dataset.parquet": "bronze.raw_geolocation",
    "product_category_name_translation.parquet": "bronze.raw_category_translation",
}


def is_olist_loaded(duckdb_path: Path) -> bool:
    """
    Check if Olist tables are already loaded.

    Returns True if all expected tables exist with non-zero row counts.
    """
    try:
        with get_connection(duckdb_path, read_only=True) as con:
            for table in OLIST_TABLE_MAP.values():
                # Check table exists
                schema, name = table.split(".")
                result = con.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = ? AND table_name = ?
                    """,
                    [schema, name],
                ).fetchone()
                if result[0] == 0:
                    return False
                # Check has rows
                count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if count == 0:
                    return False
        return True
    except Exception as e:
        logger.warning(f"Could not check Olist load state: {e}")
        return False


def load_olist_parquets(
    duckdb_path: Path,
    olist_dir: Path,
    batch_id: str,
    force: bool = False,
) -> dict[str, int]:
    """
    Load 9 Olist Parquet files into bronze tables.

    Idempotent: skips load if tables already populated, unless force=True.

    Returns:
        dict mapping table name to row count.
    """
    if not force and is_olist_loaded(duckdb_path):
        logger.info("Olist already loaded, skipping (use --force-olist to reload)")
        return {}

    counts = {}
    ingested_at = datetime.now(timezone.utc)

    with get_connection(duckdb_path) as con:
        for parquet_name, table in OLIST_TABLE_MAP.items():
            parquet_path = olist_dir / parquet_name
            if not parquet_path.exists():
                logger.error(f"Parquet not found: {parquet_path}")
                continue

            # Use DuckDB's native Parquet reader for speed
            # Add bronze metadata columns inline
            con.execute(f"DROP TABLE IF EXISTS {table}")
            con.execute(f"""
                CREATE TABLE {table} AS
                SELECT
                    *,
                    TIMESTAMP '{ingested_at.isoformat()}' AS _ingested_at,
                    '{parquet_name}' AS _source_file,
                    '{batch_id}' AS _batch_id,
                    TRUE AS _is_valid
                FROM read_parquet('{parquet_path.as_posix()}')
            """)

            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            counts[table] = count
            logger.info(f"Loaded {table}: {count:,} rows")

    total = sum(counts.values())
    logger.success(f"Olist load complete. Total: {total:,} rows across {len(counts)} tables")
    return counts


def record_pipeline_run(
    duckdb_path: Path,
    run_id: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    rows_processed: int,
    error_message: str | None = None,
) -> None:
    """Insert a row into metadata.pipeline_runs."""
    with get_connection(duckdb_path) as con:
        con.execute(
            """
            INSERT INTO metadata.pipeline_runs
            (run_id, started_at, finished_at, status, rows_processed, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [run_id, started_at, finished_at, status, rows_processed, error_message],
        )


def main(
    mode: str,
    num_events: int,
    force_olist: bool = False,
    skip_upload: bool = False,
) -> int:
    started_at = datetime.now(timezone.utc)
    batch_id = str(uuid.uuid4())
    run_id = f"ingest-{started_at.strftime('%Y%m%d-%H%M%S')}-{batch_id[:8]}"

    logger.info(f"=== Bronze ingestion run {run_id} ===")
    logger.info(f"Mode: {mode} | Events: {num_events:,} | Batch: {batch_id}")

    try:
        # Step 1: download DuckDB
        logger.info("Step 1/5 - Download DuckDB from Storage")
        download_duckdb()
        init_db(LOCAL_DUCKDB)  # ensures schemas + metadata table exist

        # Step 2: download Olist Parquets
        logger.info("Step 2/5 - Download Olist Parquets from Storage")
        download_olist_parquets()

        # Step 3: load Olist tables (idempotent)
        logger.info("Step 3/5 - Load Olist into Bronze")
        olist_counts = load_olist_parquets(
            LOCAL_DUCKDB, LOCAL_OLIST_DIR, batch_id, force=force_olist
        )

        # Step 4: generate + insert Faker clickstream
        logger.info("Step 4/5 - Generate Faker clickstream")
        df = generate_clickstream(
            mode=mode,
            olist_dir=LOCAL_OLIST_DIR,
            num_events=num_events,
            batch_id=batch_id,
        )
        write_clickstream(df, LOCAL_DUCKDB, table="bronze.raw_clickstream")
        clickstream_count = len(df)

        # Step 5: upload DuckDB
        if not skip_upload:
            logger.info("Step 5/5 - Upload DuckDB to Storage")
            upload_duckdb()
        else:
            logger.warning("Step 5/5 - Skipped upload (--skip-upload)")

        # Record success
        finished_at = datetime.now(timezone.utc)
        total_rows = sum(olist_counts.values()) + clickstream_count
        record_pipeline_run(
            LOCAL_DUCKDB, run_id, started_at, finished_at,
            "success", total_rows,
        )

        elapsed = (finished_at - started_at).total_seconds()
        logger.success(
            f"=== Run {run_id} completed in {elapsed:.1f}s | "
            f"{total_rows:,} rows total ==="
        )
        return 0

    except Exception as e:
        finished_at = datetime.now(timezone.utc)
        logger.exception(f"Ingestion failed: {e}")
        try:
            record_pipeline_run(
                LOCAL_DUCKDB, run_id, started_at, finished_at,
                "failed", 0, str(e),
            )
        except Exception:
            pass  # don't mask original error
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=["backfill", "live"], required=True,
        help="Backfill = generate 2016-2018 timestamps; Live = generate last 6h",
    )
    parser.add_argument(
        "--num-events", type=int, default=2000,
        help="Number of clickstream events to generate (default 2000)",
    )
    parser.add_argument(
        "--force-olist", action="store_true",
        help="Reload Olist tables even if already populated",
    )
    parser.add_argument(
        "--skip-upload", action="store_true",
        help="Don't upload DuckDB back to Storage (for local testing)",
    )
    args = parser.parse_args()

    sys.exit(main(
        mode=args.mode,
        num_events=args.num_events,
        force_olist=args.force_olist,
        skip_upload=args.skip_upload,
    ))