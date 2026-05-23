"""Bronze validation: Great Expectations report + per-row _is_valid flagging.

Two responsibilities:
  1. Run GE suites against each Bronze table and print a pass/fail report
     (column/aggregate-level expectations).
  2. Set the _is_valid column row-by-row using the SQL rules in
     row_validity_rules.py, so Silver can filter on it.

Run AFTER ingestion, BEFORE dbt:
    python pipeline/02_validate_bronze.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Disable tqdm progress bars (GE uses them when calculating metrics).
os.environ["TQDM_DISABLE"] = "1"

# Allow importing the expectations package from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from utils.duckdb_client import get_connection, table_exists  # noqa: E402

load_dotenv()


def _ge_report(con) -> bool:
    """Run GE suites against Bronze tables; return True if all pass.

    Imported lazily so the row-flagging path still works if GE is absent.
    """
    try:
        import great_expectations as gx

        from expectations.suites import SUITES
    except Exception as exc:  # noqa: BLE001
        print(f"  [SKIP] GE not available ({exc}); running row rules only")
        return True

    # Silence GE's per-metric progress bars for clean log output.
    import os

    os.environ.setdefault("GE_USAGE_STATISTICS_URL", "")
    try:
        from great_expectations.core import usage_statistics  # noqa: F401
    except Exception:  # noqa: BLE001
        pass
    context = gx.get_context(mode="ephemeral")
    all_pass = True

    for table, expectations in SUITES.items():
        if not table_exists(con, "bronze", table):
            continue
        df = con.execute(f"SELECT * FROM bronze.{table}").df()
        data_source = context.data_sources.add_pandas(f"src_{table}")
        asset = data_source.add_dataframe_asset(name=table)
        batch_def_obj = asset.add_batch_definition_whole_dataframe(f"bd_{table}")
        batch = batch_def_obj.get_batch(batch_parameters={"dataframe": df})

        failed = 0
        for exp in expectations:
            result = batch.validate(exp)
            if not result.success:
                failed += 1
        status = "PASS" if failed == 0 else f"{failed} FAILED"
        print(f"  [{status}] {table} ({len(expectations)} expectations)")
        if failed:
            all_pass = False

    return all_pass


def _set_validity(con) -> None:
    """Set _is_valid per row using the SQL validity rules."""
    from expectations.row_validity_rules import VALIDITY_RULES

    print("\nSetting _is_valid per row:")
    for table, rule in VALIDITY_RULES.items():
        if not table_exists(con, "bronze", table):
            continue
        con.execute(
            f"UPDATE bronze.{table} SET _is_valid = ({rule});"
        )
        counts = con.execute(
            f"SELECT count(*) FILTER (WHERE _is_valid), count(*) FROM bronze.{table}"
        ).fetchone()
        valid, total = counts
        invalid = total - valid
        print(f"  bronze.{table}: {valid}/{total} valid, {invalid} flagged invalid")


def main() -> int:
    print("=" * 56)
    print("RetailLens — Bronze validation")
    print("=" * 56)

    con = get_connection()

    print("Great Expectations suites:")
    ge_pass = _ge_report(con)

    _set_validity(con)

    con.close()
    print("=" * 56)
    print(f"GE suites: {'all PASS' if ge_pass else 'some FAILED (expected: dirty rows)'}")
    print("Row-level _is_valid set. Ready for dbt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
