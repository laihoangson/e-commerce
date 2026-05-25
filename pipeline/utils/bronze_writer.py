"""Helper for writing DataFrames to Bronze tables with metadata columns.

Every Bronze row carries 4 metadata columns. _is_valid is left NULL at
generation time; Great Expectations sets it in Phase 3.
"""

from __future__ import annotations

from datetime import datetime, timezone

import duckdb
import pandas as pd


def _add_metadata(df: pd.DataFrame, source_file: str, batch_id: str) -> pd.DataFrame:
    """Append the 4 Bronze metadata columns to a DataFrame copy."""
    out = df.copy()
    out["_ingested_at"] = datetime.now(timezone.utc)
    out["_source_file"] = source_file
    out["_batch_id"] = batch_id
    out["_is_valid"] = pd.NA  # set by Great Expectations later
    return out


def write_bronze(
    con: duckdb.DuckDBPyConnection,
    df: pd.DataFrame,
    table: str,
    source_file: str,
    batch_id: str,
    *,
    replace: bool = False,
) -> int:
    """Write a DataFrame to bronze.<table>, adding metadata columns.

    Args:
        con: DuckDB connection.
        df: data to write (without metadata columns).
        table: target table name (without schema prefix).
        source_file: logical source label for _source_file.
        batch_id: run identifier for _batch_id.
        replace: if True, drop and recreate the table; else append.

    Returns:
        Number of rows written.
    """
    enriched = _add_metadata(df, source_file, batch_id)
    con.register("_staging_df", enriched)
    fq = f"bronze.{table}"

    if replace:
        con.execute(f"DROP TABLE IF EXISTS {fq};")
        con.execute(f"CREATE TABLE {fq} AS SELECT * FROM _staging_df;")
    else:
        exists = con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema='bronze' AND table_name=?",
            [table],
        ).fetchone()
        if exists and exists[0] > 0:
            # Insert by column name (not position) so appends are robust to
            # column ordering differences between batches.
            con.execute(f"INSERT INTO {fq} BY NAME SELECT * FROM _staging_df;")
        else:
            con.execute(f"CREATE TABLE {fq} AS SELECT * FROM _staging_df;")

    con.unregister("_staging_df")
    return len(enriched)
