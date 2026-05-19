"""
scripts/inspect_bronze.py - Quick row-count summary of the bronze layer.

Usage:
    python scripts/inspect_bronze.py
    python scripts/inspect_bronze.py --schema silver    # for later weeks
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


def main(db_path: Path, schema: str) -> int:
    if not db_path.exists():
        print(f"DuckDB file not found: {db_path}")
        return 1

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = con.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = ?
            ORDER BY table_name
            """,
            [schema],
        ).fetchall()

        if not tables:
            print(f"No tables in schema '{schema}'")
            return 0

        print(f"\n{schema.upper()} layer ({len(tables)} tables):")
        print("-" * 60)

        total = 0
        for (name,) in tables:
            count = con.execute(f"SELECT COUNT(*) FROM {schema}.{name}").fetchone()[0]
            total += count
            print(f"  {name:<40} {count:>15,} rows")

        print("-" * 60)
        print(f"  {'TOTAL':<40} {total:>15,} rows\n")
    finally:
        con.close()

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/retaillens.duckdb"))
    parser.add_argument("--schema", default="bronze",
                        help="Schema to inspect (default: bronze)")
    args = parser.parse_args()
    sys.exit(main(args.db, args.schema))