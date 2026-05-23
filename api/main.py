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
def kpis() -> dict:
    """Headline KPIs for the dashboard overview section."""
    revenue = _query(
        "SELECT COALESCE(SUM(revenue),0) AS total_revenue, "
        "COALESCE(SUM(orders),0) AS total_orders, "
        "COALESCE(AVG(avg_order_value),0) AS avg_order_value FROM daily_revenue"
    )
    customers = _query("SELECT COUNT(*) AS total_customers FROM customer_ltv")
    funnel = _query("SELECT delivery_rate_pct FROM funnel_conversion LIMIT 1")
    row = revenue[0] if revenue else {}
    return {
        "total_revenue": round(float(row.get("total_revenue", 0)), 2),
        "total_orders": int(row.get("total_orders", 0)),
        "avg_order_value": round(float(row.get("avg_order_value", 0)), 2),
        "total_customers": int(customers[0]["total_customers"]) if customers else 0,
        "delivery_rate_pct": (
            float(funnel[0]["delivery_rate_pct"]) if funnel else 0.0
        ),
    }


@app.get("/api/revenue/monthly")
def revenue_monthly() -> list[dict]:
    """Revenue aggregated by month (computed from daily_revenue)."""
    return _query(
        "SELECT to_char(date_trunc('month', order_date), 'YYYY-MM') AS month, "
        "ROUND(SUM(revenue)::numeric, 2) AS revenue, SUM(orders) AS orders "
        "FROM daily_revenue GROUP BY 1 ORDER BY 1"
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
