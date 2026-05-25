"""Offline job: produce the observability report and upload it.

Combines three views into one artifact (monitoring_report.json) served to the
dashboard's System Health section:
  - drift: PSI / KS between the Olist reference and the live current data
  - slis: pipeline service-level indicators vs objectives
  - models: training metrics read from the model artifacts

Runs offline alongside the other batch jobs.

Usage:
    python monitoring/generate_monitoring.py
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

load_dotenv()

from drift import compute_drift  # noqa: E402
from monitor import collect_slis  # noqa: E402
from utils.artifact_store import download_artifact, upload_artifact  # noqa: E402
from utils.duckdb_client import get_connection  # noqa: E402

ARTIFACT_NAME = "monitoring_report.json"

DRIFT_FEATURES_SQL = """
    SELECT i.price, i.freight_value, o.delivery_days,
           (SELECT count(*) FROM main_silver.fact_order_items x
            WHERE x.order_id = o.order_id) AS items_per_order
    FROM main_silver.fact_orders o
    JOIN main_silver.fact_order_items i USING(order_id)
    WHERE o.data_source = '{source}' AND o.order_status = 'delivered'
      AND o.delivery_days >= 0
"""


def _feature_dict(con, source: str) -> dict:
    df = con.execute(DRIFT_FEATURES_SQL.format(source=source)).df()
    cols = ["price", "freight_value", "delivery_days", "items_per_order"]
    return {c: df[c].values for c in cols}


def _model_metrics() -> dict:
    """Read metrics from each model artifact, if available."""
    import io
    import joblib

    out = {}
    for name, key in [
        ("reactivation", "reactivation_xgb.joblib"),
        ("recommendation", "recommendation_als.joblib"),
    ]:
        try:
            local = download_artifact(key)
            art = joblib.load(local)
            out[name] = art.get("metrics", {})
            os.remove(local)
        except Exception as exc:  # noqa: BLE001
            out[name] = {"status": "unavailable", "error": str(exc)[:80]}
    try:
        ab_local = download_artifact("ab_results.json")
        with open(ab_local, "rb") as f:
            ab = json.loads(f.read().decode("utf-8"))
        os.remove(ab_local)
    except Exception:
        ab = None
    if ab:
        out["ab_analysis"] = {"experiments": len(ab.get("results", []))}
    return out


def main() -> int:
    con = get_connection()

    ref = _feature_dict(con, "olist")
    cur = _feature_dict(con, "faker_live")
    drift = compute_drift(ref, cur)
    slis = collect_slis(con)
    con.close()

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "drift": {
            "reference": "olist (2016-2018)",
            "current": "faker_live (2024-2026)",
            "features": [
                {"feature": d.feature, "psi": d.psi, "psi_band": d.psi_band,
                 "ks_statistic": d.ks_statistic, "ks_pvalue": d.ks_pvalue,
                 "drifted": d.drifted}
                for d in drift
            ],
            "drifted_count": sum(d.drifted for d in drift),
            "total_features": len(drift),
        },
        "slis": [
            {"name": s.name, "value": s.value, "unit": s.unit,
             "objective": s.objective, "met": s.met}
            for s in slis
        ],
        "slo_met": sum(s.met for s in slis),
        "slo_total": len(slis),
        "models": _model_metrics(),
    }

    fd, tmp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(tmp, "w") as f:
        json.dump(report, f, indent=2)
    remote = upload_artifact(tmp, ARTIFACT_NAME)
    os.remove(tmp)
    print(f"drift: {report['drift']['drifted_count']}/{report['drift']['total_features']} features drifted")
    print(f"SLO: {report['slo_met']}/{report['slo_total']} met")
    print(f"Uploaded monitoring report to {remote}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
