"""Health check — run at the start of the pipeline to verify the environment.

Checks:
  1. Required environment variables are set
  2. DuckDB opens and the medallion schemas can be created
  3. Supabase Storage connects and the bucket exists

Usage:
    python pipeline/00_health_check.py

Exit code 0 = pass, 1 = fail (so GitHub Actions can detect failures).
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

load_dotenv()

# Import after load_dotenv so the clients can read the env vars.
from utils.duckdb_client import ensure_schemas, get_connection  # noqa: E402
from utils.supabase_client import (  # noqa: E402
    check_bucket_exists,
    get_bucket_name,
    get_storage_client,
)

REQUIRED_ENV = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_BUCKET",
]


def _ok(msg: str) -> None:
    print(f"  [PASS] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def check_env() -> bool:
    import os

    print("1. Environment variables")
    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
    if missing:
        _fail(f"missing: {', '.join(missing)}")
        return False
    _ok(f"all {len(REQUIRED_ENV)} required vars present")
    return True


def check_duckdb() -> bool:
    print("2. DuckDB")
    try:
        con = get_connection()
        ensure_schemas(con)
        schemas = con.execute(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name IN ('bronze','silver','gold') ORDER BY 1"
        ).fetchall()
        con.close()
        names = [s[0] for s in schemas]
        if set(names) >= {"bronze", "silver", "gold"}:
            _ok(f"opened OK, schemas: {', '.join(names)}")
            return True
        _fail(f"missing schemas, only found: {names}")
        return False
    except Exception as exc:  # noqa: BLE001
        _fail(f"error: {exc}")
        return False


def check_supabase() -> bool:
    print("3. Supabase Storage")
    try:
        client = get_storage_client()
        bucket = get_bucket_name()
        if check_bucket_exists(client, bucket):
            _ok(f"connected OK, bucket '{bucket}' exists")
            return True
        _fail(f"connected OK but bucket '{bucket}' not found")
        return False
    except Exception as exc:  # noqa: BLE001
        _fail(f"error: {exc}")
        return False


def main() -> int:
    print("=" * 50)
    print("RetailLens — Health Check")
    print("=" * 50)

    results = [check_env(), check_duckdb(), check_supabase()]

    print("=" * 50)
    if all(results):
        print("RESULT: all checks PASS")
        return 0
    print(f"RESULT: {results.count(False)}/{len(results)} checks FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
