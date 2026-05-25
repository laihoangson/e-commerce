"""Daily live-mode orchestrator (run by GitHub Actions cron).

Steps:
  1. Restore the DuckDB warehouse from Supabase Storage (ephemeral runner).
  2. Generate today's synthetic live orders (idempotent: skips if already done).
  3. Validate Bronze (set _is_valid on new rows).
  4. Run dbt to rebuild Silver + Gold.
  5. Sync Gold marts to Supabase Postgres (so the dashboard updates).
  6. Save the updated DuckDB back to Storage.

If no warehouse exists in Storage yet (first run), it exits with guidance to run
the initial backfill locally and save it first.

Usage:
    python pipeline/run_daily_live.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv()

from utils.db_persistence import restore_duckdb, save_duckdb  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DB_PATH = os.getenv("DUCKDB_PATH", str(REPO / "data" / "retaillens.duckdb"))


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        raise SystemExit(f"Step failed: {' '.join(cmd)} (exit {result.returncode})")


def main() -> int:
    print("=" * 56)
    print("RetailLens daily live run")
    print("=" * 56)

    print("\n[1/6] Restoring DuckDB from Storage...")
    if not restore_duckdb(DB_PATH):
        print(
            "[FAIL] No warehouse found in Storage. Run the initial backfill "
            "locally (load_olist_bronze + live_generator backfill + dbt) and "
            "save it once with: python -c \"from pipeline.utils.db_persistence "
            "import save_duckdb; save_duckdb('<path>')\""
        )
        return 1
    print(f"  Restored to {DB_PATH}")

    env = dict(os.environ, DUCKDB_PATH=DB_PATH)

    print("\n[2/6] Generating today's live orders...")
    run([sys.executable, str(REPO / "pipeline" / "live_generator.py"), "--mode", "daily"])

    print("\n[3/6] Validating Bronze...")
    run([sys.executable, str(REPO / "pipeline" / "02_validate_bronze.py")])

    print("\n[4/6] Running dbt...")
    run(["dbt", "run", "--profiles-dir", "."], cwd=REPO / "dbt")

    print("\n[5/6] Syncing Gold to Postgres...")
    run([sys.executable, str(REPO / "pipeline" / "03_sync_gold.py")])

    print("\n[6/6] Saving DuckDB back to Storage...")
    remote = save_duckdb(DB_PATH)
    print(f"  Saved to {remote}")

    print("\nDaily live run complete.")
    return 0


# subprocess calls inherit DUCKDB_PATH via the environment set below.
os.environ["DUCKDB_PATH"] = DB_PATH


if __name__ == "__main__":
    sys.exit(main())
