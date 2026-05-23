"""DuckDB connection helpers.

DuckDB is the warehouse/compute layer of RetailLens. The .duckdb file lives on
Supabase Storage between runs; the pipeline downloads it locally, works on it,
then uploads it back (see storage_pipeline.py).
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

DEFAULT_DUCKDB_PATH = os.getenv("DUCKDB_PATH", "data/retaillens.duckdb")


def get_connection(db_path: str | None = None) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection, creating the parent directory if needed.

    Args:
        db_path: path to the .duckdb file. Defaults to env DUCKDB_PATH.

    Returns:
        A DuckDB connection.
    """
    path = db_path or DEFAULT_DUCKDB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(path)
    return con


def ensure_schemas(con: duckdb.DuckDBPyConnection) -> None:
    """Create the medallion schemas if they do not already exist."""
    for schema in ("bronze", "silver", "gold"):
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")


def table_exists(con: duckdb.DuckDBPyConnection, schema: str, table: str) -> bool:
    """Return True if the given table exists in the given schema."""
    result = con.execute(
        """
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema = ? AND table_name = ?
        """,
        [schema, table],
    ).fetchone()
    return bool(result and result[0] > 0)
