"""One-time generation of the four Tier 0 master tables.

Writes raw_geolocation, raw_category_translation, raw_sellers, raw_products into
the bronze schema (replace mode — idempotent).

Usage:
    python scripts/generate_masters_once.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

# Allow importing the pipeline package when run from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from dotenv import load_dotenv  # noqa: E402

from utils.bronze_writer import write_bronze  # noqa: E402
from utils.duckdb_client import ensure_schemas, get_connection  # noqa: E402
from utils.master_generator import generate_all_masters  # noqa: E402

load_dotenv()

SEED = 42


def main() -> int:
    batch_id = str(uuid.uuid4())
    print(f"Generating master tables (batch {batch_id[:8]}) ...")

    con = get_connection()
    ensure_schemas(con)
    masters = generate_all_masters(seed=SEED)

    for table, df in masters.items():
        n = write_bronze(
            con, df, table, source_file="master_generator", batch_id=batch_id, replace=True
        )
        print(f"  [OK] bronze.{table}: {n} rows")

    con.close()
    print("Master generation complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
