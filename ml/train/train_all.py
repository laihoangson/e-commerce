"""Run all three training jobs in sequence.

Trains reactivation, recommendation, and A/B analysis, uploading each artifact
to Supabase Storage. Intended to run offline (locally or via CI), separate from
the serving API.

Usage:
    python ml/train/train_all.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    import train_ab_analysis
    import train_reactivation
    import train_recommendation

    jobs = [
        ("reactivation", train_reactivation.main),
        ("recommendation", train_recommendation.main),
        ("ab_analysis", train_ab_analysis.main),
    ]
    failed = 0
    for name, fn in jobs:
        print(f"\n{'=' * 56}\nTraining: {name}\n{'=' * 56}")
        try:
            rc = fn()
            if rc != 0:
                failed += 1
                print(f"[WARN] {name} returned {rc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[FAIL] {name}: {exc}")

    print(f"\nDone. {len(jobs) - failed}/{len(jobs)} jobs succeeded.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
