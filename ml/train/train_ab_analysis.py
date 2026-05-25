"""Compute A/B experiment statistical results and upload as an artifact.

Unlike the other two, A/B has no fitted model - it is a statistical analysis.
This script runs the tests (Welch t-test, Mann-Whitney U, 95% CI) over the
live-tail experiment data and persists the results as JSON, which the API then
serves. Keeping it as an "artifact" keeps the serving path uniform.

Usage:
    python ml/train/train_ab_analysis.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipeline"))
load_dotenv()

from utils.artifact_store import upload_artifact  # noqa: E402
from utils.duckdb_client import get_connection  # noqa: E402

ARTIFACT_NAME = "ab_results.json"


def main() -> int:
    from scipy import stats

    con = get_connection()
    ab = con.execute(
        """
        SELECT o.ab_experiment AS experiment, o.ab_variant AS variant,
               sum(i.item_total) AS order_value
        FROM main_silver.fact_orders o
        JOIN main_silver.fact_order_items i USING(order_id)
        WHERE o.ab_experiment IS NOT NULL
        GROUP BY o.order_id, o.ab_experiment, o.ab_variant
        """
    ).df()
    con.close()

    results = []
    for exp in sorted(ab["experiment"].unique()):
        sub = ab[ab["experiment"] == exp]
        a = sub[sub["variant"] == "A"]["order_value"].values
        b = sub[sub["variant"] == "B"]["order_value"].values
        t_p = float(stats.ttest_ind(a, b, equal_var=False).pvalue)
        u_p = float(stats.mannwhitneyu(a, b, alternative="two-sided").pvalue)
        diff = float(b.mean() - a.mean())
        se = float(np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))
        results.append({
            "experiment": exp,
            "n_a": int(len(a)), "n_b": int(len(b)),
            "mean_a": round(float(a.mean()), 2), "mean_b": round(float(b.mean()), 2),
            "lift_pct": round(100 * diff / a.mean(), 2),
            "ttest_p": round(t_p, 4),
            "mannwhitney_p": round(u_p, 4),
            "ci95_low": round(diff - 1.96 * se, 2),
            "ci95_high": round(diff + 1.96 * se, 2),
            "significant": bool(t_p < 0.05),
        })
        print(f"{exp}: lift={results[-1]['lift_pct']}%  p={results[-1]['ttest_p']}  "
              f"{'SIGNIFICANT' if results[-1]['significant'] else 'not significant'}")

    artifact = {"results": results, "computed_at": datetime.utcnow().isoformat()}
    fd, tmp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(tmp, "w") as f:
        json.dump(artifact, f, indent=2)
    remote = upload_artifact(tmp, ARTIFACT_NAME)
    os.remove(tmp)
    print(f"Uploaded artifact to Storage: {remote}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
