"""
DuckDB client wrapper for RetailLens.

The DuckDB file is the "lakehouse-in-a-file" - it lives on Supabase Storage
between pipeline runs and is downloaded at the start of each run.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import duckdb
from loguru import logger

DEFAULT_DB_PATH = Path("data/retaillens.duckdb")
SCHEMAS = ("bronze", "silver", "gold", "metadata")


@contextmanager
def get_connection(db_path: str | Path = DEFAULT_DB_PATH, read_only: bool = False):
    """Yield a DuckDB connection. Auto-creates schemas on first use."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_path), read_only=read_only)
    try:
        if not read_only:
            for schema in SCHEMAS:
                con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        yield con
    finally:
        con.close()


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    """Initialize the DuckDB file with empty schemas + metadata table."""
    with get_connection(db_path) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata.pipeline_runs (
                run_id VARCHAR PRIMARY KEY,
                started_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP,
                status VARCHAR,
                rows_processed BIGINT,
                error_message VARCHAR
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata.health_check (
                checked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source VARCHAR NOT NULL,
                status VARCHAR NOT NULL
            )
            """
        )
        logger.success(f"Initialized DuckDB at {db_path}")


def health_check(db_path: str | Path = DEFAULT_DB_PATH) -> bool:
    """Verify DuckDB file is readable and writable."""
    try:
        with get_connection(db_path) as con:
            con.execute(
                """
                INSERT INTO metadata.health_check (source, status)
                VALUES ('duckdb_health_check', 'ok')
                """
            )
            count = con.execute(
                "SELECT COUNT(*) FROM metadata.health_check"
            ).fetchone()[0]
            logger.success(f"DuckDB OK - health_check row count: {count}")
        return True
    except Exception as e:
        logger.error(f"DuckDB health check failed: {e}")
        return False


if __name__ == "__main__":
    import sys

    init_db()
    sys.exit(0 if health_check() else 1)