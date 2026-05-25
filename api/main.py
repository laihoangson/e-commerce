"""RetailLens API — FastAPI serving layer.

Serves computed/aggregate endpoints that are awkward to express as plain REST
queries. Simple charts read Supabase REST directly; this layer handles the rest
and will host ML inference from Phase 5.

Reads from Supabase Postgres (the Gold serving layer) via SUPABASE_DB_URL.

Run locally:
    cd api
    uvicorn main:app --reload

Deployed on Render (see render.yaml).
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

load_dotenv()


def _build_engine() -> Engine:
    """Create a SQLAlchemy engine for Supabase Postgres from SUPABASE_DB_URL."""
    url = os.getenv("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError("Missing SUPABASE_DB_URL")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    return create_engine(url, pool_pre_ping=True)


app = FastAPI(title="RetailLens API", version="1.0.0")

# Allow the GitHub Pages dashboard (and local dev) to call the API.
ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS", "*"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Lazily-created engine so import never fails when env is absent.
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def _query(sql: str, params: dict | None = None) -> list[dict]:
    """Run a read-only query and return rows as a list of dicts."""
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            result = conn.execute(text(sql), params or {})
            cols = result.keys()
            return [dict(zip(cols, row)) for row in result.fetchall()]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"query failed: {exc}") from exc


@app.get("/")
def root() -> dict:
    """Service metadata."""
    return {"service": "RetailLens API", "version": "1.0.0", "status": "ok"}


@app.get("/health")
def health() -> dict:
    """Health check: verify the database is reachable."""
    try:
        _query("SELECT 1 AS ok")
        return {"status": "healthy", "database": "connected"}
    except HTTPException:
        return {"status": "degraded", "database": "unreachable"}


@app.get("/api/kpis")
def kpis(source: str = "olist") -> dict:
    """Headline KPIs for a dashboard tab, filtered by data source.

    source: 'olist' (real historical) or 'faker_live' (synthetic live tail).
    """
    rev = _query(
        "SELECT COALESCE(SUM(revenue),0) AS total_revenue, "
        "COALESCE(SUM(orders),0) AS total_orders, "
        "COALESCE(AVG(avg_order_value),0) AS avg_order_value "
        "FROM daily_revenue WHERE data_source = :src",
        {"src": source},
    )
    funnel = _query(
        "SELECT delivery_rate_pct FROM funnel_conversion WHERE data_source = :src",
        {"src": source},
    )
    row = rev[0] if rev else {}
    return {
        "source": source,
        "total_revenue": round(float(row.get("total_revenue", 0)), 2),
        "total_orders": int(row.get("total_orders", 0)),
        "avg_order_value": round(float(row.get("avg_order_value", 0)), 2),
        "delivery_rate_pct": float(funnel[0]["delivery_rate_pct"]) if funnel else 0.0,
    }


@app.get("/api/revenue/monthly")
def revenue_monthly(source: str = "olist") -> list[dict]:
    """Revenue aggregated by month for a data source."""
    return _query(
        "SELECT to_char(date_trunc('month', order_date), 'YYYY-MM') AS month, "
        "ROUND(SUM(revenue)::numeric, 2) AS revenue, SUM(orders) AS orders "
        "FROM daily_revenue WHERE data_source = :src GROUP BY 1 ORDER BY 1",
        {"src": source},
    )


@app.get("/api/funnel")
def funnel(source: str = "olist") -> dict:
    """Order funnel for a data source."""
    rows = _query(
        "SELECT purchased, approved, shipped, delivered, delivery_rate_pct "
        "FROM funnel_conversion WHERE data_source = :src",
        {"src": source},
    )
    return rows[0] if rows else {}


@app.get("/api/delivery-performance")
def delivery_performance(source: str = "olist") -> dict:
    """Delivery performance metrics for a data source."""
    rows = _query(
        "SELECT delivered_orders, avg_delivery_days, late_orders, late_rate_pct "
        "FROM delivery_performance WHERE data_source = :src",
        {"src": source},
    )
    return rows[0] if rows else {}


@app.get("/api/review-analysis")
def review_analysis(source: str = "olist") -> list[dict]:
    """Review score distribution and late-delivery correlation for a source."""
    return _query(
        "SELECT review_score, reviews, pct_late FROM review_analysis "
        "WHERE data_source = :src ORDER BY review_score",
        {"src": source},
    )


@app.get("/api/revenue-by-state")
def revenue_by_state(source: str = "olist") -> list[dict]:
    """Revenue and orders by Brazilian state, for the choropleth map."""
    return _query(
        "SELECT state, orders, revenue FROM revenue_by_state "
        "WHERE data_source = :src ORDER BY revenue DESC",
        {"src": source},
    )


@app.get("/api/ab-tests")
def ab_tests() -> list[dict]:
    """A/B test results with computed lift of variant B over variant A."""
    rows = _query("SELECT * FROM ab_test_results ORDER BY ab_experiment, ab_variant")
    # Group by experiment, compute lift on avg_order_value (B vs A).
    by_exp: dict[str, dict] = {}
    for r in rows:
        exp = r["ab_experiment"]
        by_exp.setdefault(exp, {})[r["ab_variant"]] = r
    out = []
    for exp, variants in by_exp.items():
        a = variants.get("A")
        b = variants.get("B")
        lift = None
        if a and b and float(a["avg_order_value"]) != 0:
            lift = round(
                100.0
                * (float(b["avg_order_value"]) - float(a["avg_order_value"]))
                / float(a["avg_order_value"]),
                2,
            )
        out.append(
            {
                "experiment": exp,
                "variant_a": a,
                "variant_b": b,
                "aov_lift_pct": lift,
            }
        )
    return out


@app.get("/api/customer-segments")
def customer_segments() -> list[dict]:
    """RFM segment counts: customers bucketed by combined R/F/M score."""
    return _query(
        "SELECT (r_score + f_score + m_score) AS rfm_total, "
        "COUNT(*) AS customers, ROUND(AVG(monetary)::numeric, 2) AS avg_monetary "
        "FROM customer_ltv GROUP BY 1 ORDER BY 1"
    )


@app.get("/api/cohort-retention")
def cohort_retention() -> dict:
    """Cohort retention as a heatmap-ready structure.

    Returns retention as a percentage of each cohort's month-0 size, so cohorts
    of different sizes are comparable.
    """
    rows = _query(
        "SELECT to_char(cohort_month, 'YYYY-MM') AS cohort, "
        "month_offset, active_customers "
        "FROM cohort_retention ORDER BY cohort_month, month_offset"
    )
    # Pivot into {cohort: {offset: count}} and compute size at offset 0.
    cohorts: dict[str, dict[int, int]] = {}
    for r in rows:
        cohorts.setdefault(r["cohort"], {})[int(r["month_offset"])] = int(
            r["active_customers"]
        )
    max_offset = max((o for c in cohorts.values() for o in c), default=0)
    grid = []
    for cohort in sorted(cohorts):
        base = cohorts[cohort].get(0, 0) or 1
        cells = []
        for off in range(max_offset + 1):
            cnt = cohorts[cohort].get(off)
            cells.append(
                None if cnt is None else round(100.0 * cnt / base, 1)
            )
        grid.append({"cohort": cohort, "size": cohorts[cohort].get(0, 0), "cells": cells})
    return {"max_offset": max_offset, "rows": grid}


@app.get("/api/sellers/top")
def sellers_top(limit: int = 10) -> list[dict]:
    """Top sellers by total revenue."""
    return _query(
        "SELECT seller_id, seller_state, total_orders, total_revenue, "
        "avg_review_score FROM seller_metrics "
        "ORDER BY total_revenue DESC LIMIT :lim",
        {"lim": limit},
    )


# ---------------------------------------------------------------------------
# ML serving layer
#
# Models are trained offline and stored on Supabase Storage under models/.
# The API downloads them lazily on first use and caches them in memory. This is
# the train-offline / serve-online pattern; training never happens in the API.
# ---------------------------------------------------------------------------

import json as _json
from functools import lru_cache

from pydantic import BaseModel

MODELS_PREFIX = "models"


def _download_artifact_bytes(remote_name: str) -> bytes:
    """Download models/<remote_name> from Supabase Storage as raw bytes."""
    from supabase import create_client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    bucket = os.getenv("SUPABASE_BUCKET", "retaillens-artifacts")
    if not url or not key:
        raise HTTPException(503, "Storage credentials not configured")
    client = create_client(url, key)
    return client.storage.from_(bucket).download(f"{MODELS_PREFIX}/{remote_name}")


@lru_cache(maxsize=1)
def _reactivation_artifact():
    import io
    import joblib
    data = _download_artifact_bytes("reactivation_xgb.joblib")
    return joblib.load(io.BytesIO(data))


@lru_cache(maxsize=1)
def _recommendation_artifact():
    import io
    import joblib
    data = _download_artifact_bytes("recommendation_als.joblib")
    return joblib.load(io.BytesIO(data))


@lru_cache(maxsize=1)
def _ab_artifact() -> dict:
    return _json.loads(_download_artifact_bytes("ab_results.json").decode("utf-8"))


class ReactivationInput(BaseModel):
    frequency: float
    recency_days: float
    tenure_days: float
    monetary: float
    avg_order_value: float
    avg_review: float


@app.get("/api/ml/status")
def ml_status() -> dict:
    """Report which model artifacts are loadable and their training metrics."""
    out = {}
    for name, loader in [
        ("reactivation", _reactivation_artifact),
        ("recommendation", _recommendation_artifact),
        ("ab_analysis", _ab_artifact),
    ]:
        try:
            art = loader()
            out[name] = art.get("metrics", {"status": "loaded"}) if isinstance(art, dict) else {"status": "loaded"}
        except Exception as exc:  # noqa: BLE001
            out[name] = {"status": "unavailable", "error": str(exc)[:120]}
    return out


@app.post("/api/predict/reactivation")
def predict_reactivation(payload: ReactivationInput) -> dict:
    """Real-time reactivation probability for a single customer's features."""
    import pandas as pd
    art = _reactivation_artifact()
    model, features = art["model"], art["features"]
    row = pd.DataFrame([[getattr(payload, f) for f in features]], columns=features)
    proba = float(model.predict_proba(row)[:, 1][0])
    return {"reactivation_probability": round(proba, 4),
            "will_reactivate": bool(proba >= 0.5)}


@app.get("/api/reactivation/top-targets")
def reactivation_top_targets(limit: int = 20) -> list[dict]:
    """Customers most likely to reactivate - precomputed at training time."""
    art = _reactivation_artifact()
    targets = art.get("top_targets", [])[:limit]
    return targets


@app.get("/api/recommend/{customer_id}")
def recommend(customer_id: str, n: int = 10) -> dict:
    """Top-N recommendations for a customer; cold-start falls back to popular.

    Recommendations are precomputed at training time and served by lookup.
    """
    art = _recommendation_artifact()
    precomputed = art.get("precomputed", {})
    if customer_id in precomputed:
        return {"customer_id": customer_id, "cold_start": False,
                "recommendations": precomputed[customer_id][:n]}
    return {"customer_id": customer_id, "cold_start": True,
            "recommendations": art.get("top_popular", [])[:n]}


@app.get("/api/ab-results")
def ab_results() -> list[dict]:
    """Served A/B statistical results (computed offline by the analysis job)."""
    return _ab_artifact().get("results", [])
