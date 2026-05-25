"""Shared feature engineering for the reactivation model.

Used by both the training script and the serving endpoint so that features are
computed identically (no train/serve skew). Given a DuckDB connection and a
cutoff date, produces the customer-level feature table for the repeat base.
"""

from __future__ import annotations

import pandas as pd

FEATURES = [
    "frequency",
    "recency_days",
    "tenure_days",
    "monetary",
    "avg_order_value",
    "avg_review",
]
MIN_ORDERS = 2


def build_features(con, cutoff: pd.Timestamp, silver_schema: str = "main_silver") -> pd.DataFrame:
    """Build the reactivation feature table from orders on or before cutoff.

    Returns a DataFrame with one row per repeat customer (>= MIN_ORDERS orders),
    the FEATURES columns, and the customer_unique_id.
    """
    obs = con.execute(
        f"""
        WITH obs AS (
            SELECT customer_unique_id AS customer, order_id,
                   order_purchase_timestamp AS ts
            FROM {silver_schema}.fact_orders
            WHERE customer_unique_id IS NOT NULL AND order_status = 'delivered'
              AND order_purchase_timestamp <= TIMESTAMP '{cutoff}'
        ),
        ov AS (SELECT order_id, sum(item_total) v
               FROM {silver_schema}.fact_order_items GROUP BY 1),
        rv AS (SELECT order_id, avg(review_score) s
               FROM {silver_schema}.fact_reviews GROUP BY 1)
        SELECT obs.customer, obs.order_id, obs.ts,
               COALESCE(ov.v, 0) AS value, rv.s AS review
        FROM obs LEFT JOIN ov USING(order_id) LEFT JOIN rv USING(order_id)
        """
    ).df()
    obs["ts"] = pd.to_datetime(obs["ts"])

    feat = obs.groupby("customer").agg(
        frequency=("order_id", "nunique"),
        recency_days=("ts", lambda s: (cutoff - s.max()).days),
        tenure_days=("ts", lambda s: (cutoff - s.min()).days),
        monetary=("value", "sum"),
        avg_review=("review", "mean"),
    ).reset_index()
    feat["avg_order_value"] = feat["monetary"] / feat["frequency"]
    feat["avg_review"] = feat["avg_review"].fillna(feat["avg_review"].median())
    feat = feat[feat["frequency"] >= MIN_ORDERS].reset_index(drop=True)
    return feat


def add_labels(feat: pd.DataFrame, con, cutoff: pd.Timestamp,
               silver_schema: str = "main_silver") -> pd.DataFrame:
    """Add the binary reactivation label from the prediction window."""
    future = con.execute(
        f"""
        SELECT DISTINCT customer_unique_id AS customer
        FROM {silver_schema}.fact_orders
        WHERE customer_unique_id IS NOT NULL AND order_status = 'delivered'
          AND order_purchase_timestamp > TIMESTAMP '{cutoff}'
        """
    ).df()["customer"]
    future_set = set(future)
    out = feat.copy()
    out["label"] = out["customer"].isin(future_set).astype(int)
    return out
