"""
pipeline/01_ingest_bronze.py - Bronze layer ingestion (refactored W2.1).

Architecture (lakehouse pattern):
    - Olist tables: VIEWs over Parquet files on Supabase Storage
      (downloaded fresh each run, queried via DuckDB native Parquet reader)
    - Clickstream: real TABLE in DuckDB (append-only, dynamic data)
    - Metadata: TABLE in DuckDB (pipeline_runs, health_check)

Why VIEWs for Olist:
    1. DuckDB file stays small (<10MB), well under Supabase free 50MB upload cap
    2. Parquet is the source of truth - no duplicate persistence
    3. Standard lakehouse pattern (like Athena/Trino over S3)
    4. Silver/Gold queries work identically whether source is TABLE or VIEW

Orchestrates:
    1. Download retaillens.duckdb from Supabase Storage (or start fresh)
    2. Download Olist Parquet files to local data/raw/olist/
    3. Register Olist tables as VIEWs over the Parquet files
    4. Generate Faker clickstream events and append to bronze.raw_clickstream
    5. Upload updated DuckDB back to Supabase Storage

Run locally:
    python pipeline/01_ingest_bronze.py --mode backfill --num-events 50000
    python pipeline/01_ingest_bronze.py --mode live --num-events 2000
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb
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
    download_duckdb,
    download_olist_parquets,
    upload_duckdb,
)

load_dotenv()


# Mapping: Parquet filename -> bronze VIEW name
OLIST_VIEW_MAP = {
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


def register_olist_views(
    duckdb_path: Path,
    olist_dir: Path,
    batch_id: str,
) -> dict[str, int]:
    """Register Olist Parquet files as VIEWs in the bronze schema."""
    counts = {}
    ingested_at = datetime.now(timezone.utc)

    with get_connection(duckdb_path) as con:
        for parquet_name, view in OLIST_VIEW_MAP.items():
            parquet_path = olist_dir / parquet_name
            if not parquet_path.exists():
                logger.error(f"Parquet not found: {parquet_path}")
                continue

            parquet_uri = parquet_path.as_posix()

            con.execute(f"""
                CREATE OR REPLACE VIEW {view} AS
                SELECT
                    *,
                    TIMESTAMP '{ingested_at.isoformat()}' AS _ingested_at,
                    '{parquet_name}' AS _source_file,
                    '{batch_id}' AS _batch_id,
                    TRUE AS _is_valid
                FROM read_parquet('{parquet_uri}')
            """)

            count = con.execute(f"SELECT COUNT(*) FROM {view}").fetchone()[0]
            counts[view] = count
            logger.info(f"Registered VIEW {view}: {count:,} rows (via Parquet)")

    total = sum(counts.values())
    logger.success(
        f"Olist views registered. Total: {total:,} rows across {len(counts)} views"
    )
    return counts


def drop_legacy_olist_tables(duckdb_path: Path) -> int:
    """One-time cleanup: drop old bronze TABLEs from broken previous runs."""
    dropped = 0
    with get_connection(duckdb_path) as con:
        for view in OLIST_VIEW_MAP.values():
            schema, name = view.split(".")
            result = con.execute(
                """
                SELECT table_type
                FROM information_schema.tables
                WHERE table_schema = ? AND table_name = ?
                """,
                [schema, name],
            ).fetchone()

            if result is None:
                continue

            table_type = result[0]
            if table_type == "BASE TABLE":
                con.execute(f"DROP TABLE {view}")
                dropped += 1
                logger.warning(
                    f"Dropped legacy TABLE {view} (will be re-created as VIEW)"
                )

        if dropped > 0:
            con.execute("CHECKPOINT")
            logger.info(f"Reclaimed space after dropping {dropped} legacy TABLE(s)")

    return dropped


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
    skip_upload: bool = False,
) -> int:
    started_at = datetime.now(timezone.utc)
    batch_id = str(uuid.uuid4())
    run_id = f"ingest-{started_at.strftime('%Y%m%d-%H%M%S')}-{batch_id[:8]}"

    logger.info(f"=== Bronze ingestion run {run_id} ===")
    logger.info(f"Mode: {mode} | Events: {num_events:,} | Batch: {batch_id}")

    try:
        logger.info("Step 1/6 - Download DuckDB from Storage")
        download_duckdb()
        init_db(LOCAL_DUCKDB)

        logger.info("Step 2/6 - Drop legacy Olist TABLEs (if any)")
        dropped = drop_legacy_olist_tables(LOCAL_DUCKDB)
        if dropped:
            logger.info(f"Cleaned {dropped} legacy table(s) from previous runs")

        logger.info("Step 3/6 - Download Olist Parquets from Storage")
        download_olist_parquets()

        logger.info("Step 4/6 - Register Olist as VIEWs over Parquet")
        olist_counts = register_olist_views(LOCAL_DUCKDB, LOCAL_OLIST_DIR, batch_id)

        logger.info("Step 5/6 - Generate Faker clickstream")
        df = generate_clickstream(
            mode=mode,
            olist_dir=LOCAL_OLIST_DIR,
            num_events=num_events,
            batch_id=batch_id,
        )
        write_clickstream(df, LOCAL_DUCKDB, table="bronze.raw_clickstream")
        clickstream_count = len(df)

        if not skip_upload:
            logger.info("Step 6/6 - Upload DuckDB to Storage")
            db_size_mb = LOCAL_DUCKDB.stat().st_size / 1024 / 1024
            logger.info(f"DuckDB file size: {db_size_mb:.2f} MB")
            upload_duckdb()
        else:
            logger.warning("Step 6/6 - Skipped upload (--skip-upload)")

        finished_at = datetime.now(timezone.utc)
        total_rows = sum(olist_counts.values()) + clickstream_count
        record_pipeline_run(
            LOCAL_DUCKDB, run_id, started_at, finished_at,
            "success", total_rows,
        )

        elapsed = (finished_at - started_at).total_seconds()
        logger.success(
            f"=== Run {run_id} completed in {elapsed:.1f}s | "
            f"{total_rows:,} rows queryable (clickstream: {clickstream_count:,} persisted) ==="
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
            pass
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
        "--skip-upload", action="store_true",
        help="Don't upload DuckDB back to Storage (for local testing)",
    )
    args = parser.parse_args()

    sys.exit(main(
        mode=args.mode,
        num_events=args.num_events,
        skip_upload=args.skip_upload,
    ))