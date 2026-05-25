"""Train the reactivation model and upload the artifact to Supabase Storage.

Offline training: reads Silver from local DuckDB, builds features (repeat base,
90-day window), trains XGBoost with class weighting, evaluates with PR-AUC, and
persists a joblib artifact (model + feature list + metrics) to Storage.

Usage:
    python ml/train/train_reactivation.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipeline"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

load_dotenv()

from reactivation_features import FEATURES, add_labels, build_features  # noqa: E402
from utils.artifact_store import upload_artifact  # noqa: E402
from utils.duckdb_client import get_connection  # noqa: E402

WINDOW_DAYS = 90
ARTIFACT_NAME = "reactivation_xgb.joblib"


def main() -> int:
    from sklearn.metrics import average_precision_score, roc_auc_score
    from sklearn.model_selection import train_test_split
    from xgboost import XGBClassifier

    con = get_connection()
    max_date = pd.to_datetime(
        con.execute(
            "SELECT max(order_purchase_timestamp) FROM main_silver.fact_orders "
            "WHERE order_status = 'delivered'"
        ).fetchone()[0]
    )
    cutoff = max_date - pd.Timedelta(days=WINDOW_DAYS)
    print(f"max_date={max_date.date()}  cutoff={cutoff.date()}")

    feat = build_features(con, cutoff)
    feat = add_labels(feat, con, cutoff)
    con.close()
    print(f"repeat base: {len(feat)}  positive rate: {feat['label'].mean():.2%}")

    X, y = feat[FEATURES], feat["label"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )
    spw = (len(y_train) - y_train.sum()) / max(y_train.sum(), 1)
    model = XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.9, colsample_bytree=0.9,
        scale_pos_weight=spw, eval_metric="aucpr",
        random_state=42, n_jobs=-1,
    )
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)[:, 1]
    metrics = {
        "pr_auc": round(float(average_precision_score(y_test, proba)), 4),
        "roc_auc": round(float(roc_auc_score(y_test, proba)), 4),
        "baseline_pr_auc": round(float(y_test.mean()), 4),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "positive_rate": round(float(y.mean()), 4),
        "trained_at": datetime.utcnow().isoformat(),
        "window_days": WINDOW_DAYS,
    }
    print(f"PR-AUC={metrics['pr_auc']} (baseline {metrics['baseline_pr_auc']})  "
          f"ROC-AUC={metrics['roc_auc']}")

    artifact = {"model": model, "features": FEATURES, "metrics": metrics}

    # Score the full repeat base so the API can serve a top-targets list without
    # needing Silver access at serving time. Keep it compact.
    feat = feat.copy()
    feat["score"] = model.predict_proba(feat[FEATURES])[:, 1]
    top = (
        feat.sort_values("score", ascending=False)
        .head(200)[["customer", "score", "frequency", "recency_days", "monetary"]]
        .round({"score": 4, "monetary": 2})
    )
    artifact["top_targets"] = top.to_dict(orient="records")

    fd, tmp = tempfile.mkstemp(suffix=".joblib")
    os.close(fd)
    joblib.dump(artifact, tmp)
    remote = upload_artifact(tmp, ARTIFACT_NAME)
    os.remove(tmp)
    print(f"Uploaded artifact to Storage: {remote}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
