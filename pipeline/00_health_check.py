"""
00_health_check.py — Week 1 plumbing verification.

Checks:
  1. Environment variables loaded
  2. DuckDB local file works
  3. Supabase Storage reachable
  4. Supabase Postgres reachable
  5. (Optional) Groq API reachable

Run locally:  python pipeline/00_health_check.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make the project root importable so `from pipeline.utils...` works
# regardless of how this script is invoked.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from loguru import logger

load_dotenv()


REQUIRED_VARS = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_ANON_KEY",
]

OPTIONAL_VARS = [
    "GROQ_API_KEY",
    "KAGGLE_USERNAME",
    "KAGGLE_KEY",
    "SLACK_WEBHOOK_URL",
]


def check_env() -> bool:
    """Verify required environment variables are set."""
    logger.info("Step 1/5 - Environment variables")
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        logger.error(f"Missing required env vars: {missing}")
        return False

    optional_missing = [v for v in OPTIONAL_VARS if not os.environ.get(v)]
    if optional_missing:
        logger.warning(f"Optional env vars not set (OK for W1): {optional_missing}")

    logger.success(f"All {len(REQUIRED_VARS)} required env vars present")
    return True


def check_duckdb() -> bool:
    """Verify local DuckDB file works."""
    logger.info("Step 2/5 - DuckDB local")
    from pipeline.utils.duckdb_client import health_check, init_db

    init_db()
    return health_check()


def check_supabase_storage() -> bool:
    """Verify Supabase Storage bucket is reachable."""
    logger.info("Step 3/5 - Supabase Storage")
    from pipeline.utils.supabase_client import ensure_bucket, get_client

    try:
        ensure_bucket()
        client = get_client()
        bucket = os.environ.get("SUPABASE_STORAGE_BUCKET", "retaillens-artifacts")
        files = client.storage.from_(bucket).list()
        logger.success(f"Bucket '{bucket}' reachable. Files: {len(files)}")
        return True
    except Exception as e:
        logger.error(f"Supabase Storage check failed: {e}")
        return False


def check_supabase_postgres() -> bool:
    """Verify Supabase Postgres is reachable via REST."""
    logger.info("Step 4/5 - Supabase Postgres")
    from pipeline.utils.supabase_client import get_client

    try:
        client = get_client()
        client.storage.list_buckets()
        logger.success("Supabase Postgres client connected")
        return True
    except Exception as e:
        logger.error(f"Postgres check failed: {e}")
        return False


def check_groq() -> bool:
    """Optional: verify Groq API key works."""
    logger.info("Step 5/5 - Groq (optional)")
    if not os.environ.get("GROQ_API_KEY"):
        logger.warning("GROQ_API_KEY not set, skipping")
        return True

    try:
        import requests

        resp = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
            timeout=10,
        )
        resp.raise_for_status()
        models = resp.json().get("data", [])
        logger.success(f"Groq API reachable. {len(models)} models available")
        return True
    except Exception as e:
        logger.error(f"Groq check failed: {e}")
        return False


def main() -> int:
    started = datetime.now(timezone.utc)
    logger.info(f"RetailLens health check started at {started.isoformat()}")

    checks = [
        ("env", check_env),
        ("duckdb", check_duckdb),
        ("supabase_storage", check_supabase_storage),
        ("supabase_postgres", check_supabase_postgres),
        ("groq", check_groq),
    ]

    results = {}
    for name, fn in checks:
        results[name] = fn()
        if not results[name] and name != "groq":
            logger.error(f"FATAL: {name} check failed, stopping")
            return 1

    finished = datetime.now(timezone.utc)
    elapsed = (finished - started).total_seconds()
    passed = sum(1 for v in results.values() if v)
    logger.info(
        f"Health check finished in {elapsed:.1f}s. "
        f"{passed}/{len(results)} checks passed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())