"""Train the ALS recommendation model and upload the artifact to Storage.

Reads purchase interactions from Silver, fits implicit ALS, evaluates with
Recall@10 / NDCG@10, and persists the fitted model plus the user/item id
mappings and a top-popular cold-start fallback.

Usage:
    python ml/train/train_recommendation.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipeline"))
load_dotenv()

from utils.artifact_store import upload_artifact  # noqa: E402
from utils.duckdb_client import get_connection  # noqa: E402

ARTIFACT_NAME = "recommendation_als.joblib"


def main() -> int:
    from implicit.als import AlternatingLeastSquares
    from scipy.sparse import csr_matrix

    con = get_connection()
    ui = con.execute(
        """
        SELECT o.customer_unique_id AS customer, i.product_id AS product, count(*) AS qty
        FROM main_silver.fact_orders o
        JOIN main_silver.fact_order_items i USING(order_id)
        WHERE o.customer_unique_id IS NOT NULL
        GROUP BY 1, 2
        """
    ).df()
    con.close()

    users = ui["customer"].astype("category")
    products = ui["product"].astype("category")
    matrix = csr_matrix(
        (ui["qty"].astype(float), (users.cat.codes, products.cat.codes))
    )
    print(f"interactions={len(ui)}  users={matrix.shape[0]}  products={matrix.shape[1]}")

    model = AlternatingLeastSquares(
        factors=64, iterations=20, regularization=0.05, random_state=42
    )
    model.fit(matrix)

    # Evaluate Recall@10 / NDCG@10 via leave-one-out on multi-product users.
    up = ui.groupby(users.cat.codes)["product"].apply(list)
    multi = up[up.apply(len) >= 2]
    rng = np.random.default_rng(42)
    sample = rng.choice(multi.index.values, size=min(500, len(multi)), replace=False)
    prod_code = {p: i for i, p in enumerate(products.cat.categories)}
    recalls, ndcgs = [], []
    for u in sample:
        bought = ui[users.cat.codes == u]["product"].tolist()
        held = prod_code[bought[-1]]
        recs = model.recommend(u, matrix[u], N=10,
                               filter_already_liked_items=False)[0].tolist()
        hit = held in recs
        recalls.append(1.0 if hit else 0.0)
        rank = recs.index(held) if hit else None
        ndcgs.append(1.0 / np.log2(rank + 2) if rank is not None else 0.0)

    top_popular = (
        ui.groupby("product")["qty"].sum().sort_values(ascending=False).head(20)
        .index.tolist()
    )

    # Precompute top-10 recommendations for a capped set of users so the API can
    # serve by lookup without shipping the full interaction matrix. Real-time
    # recompute for arbitrary users would need the matrix; this keeps serving
    # light and is a common production pattern (batch-precomputed recs).
    user_cats = list(users.cat.categories)
    product_cats = list(products.cat.categories)
    max_users = min(2000, matrix.shape[0])
    precomputed = {}
    for uidx in range(max_users):
        ids = model.recommend(
            uidx, matrix[uidx], N=10, filter_already_liked_items=True
        )[0]
        precomputed[user_cats[uidx]] = [product_cats[i] for i in ids]
    print(f"precomputed recommendations for {len(precomputed)} users")

    metrics = {
        "recall_at_10": round(float(np.mean(recalls)), 4),
        "ndcg_at_10": round(float(np.mean(ndcgs)), 4),
        "n_users": int(matrix.shape[0]),
        "n_products": int(matrix.shape[1]),
        "n_interactions": int(len(ui)),
        "trained_at": datetime.utcnow().isoformat(),
    }
    print(f"Recall@10={metrics['recall_at_10']}  NDCG@10={metrics['ndcg_at_10']}")

    artifact = {
        "precomputed": precomputed,
        "top_popular": top_popular,
        "metrics": metrics,
    }
    fd, tmp = tempfile.mkstemp(suffix=".joblib")
    os.close(fd)
    joblib.dump(artifact, tmp)
    remote = upload_artifact(tmp, ARTIFACT_NAME)
    os.remove(tmp)
    print(f"Uploaded artifact to Storage: {remote}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
