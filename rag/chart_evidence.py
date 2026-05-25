"""Build evidence strings for each dashboard chart from Gold data.

The evidence string states a chart's key numbers in plain language. It is both
the input the LLM may use to write claims and the premise the NLI verifier
checks claims against. Keeping these numbers factual and self-contained is what
makes verification meaningful.
"""

from __future__ import annotations

import pandas as pd


def revenue_evidence(con, schema: str, source: str) -> str:
    df = con.execute(
        f"SELECT order_date, revenue, orders FROM {schema}.daily_revenue "
        f"WHERE data_source = '{source}'"
    ).df()
    if df.empty:
        return "No revenue data."
    total = df["revenue"].sum()
    monthly = df.assign(m=pd.to_datetime(df["order_date"]).dt.to_period("M")).groupby("m")["revenue"].sum()
    peak_m, low_m = monthly.idxmax(), monthly.idxmin()
    return (
        f"Total revenue is {total:,.0f} BRL across {int(df['orders'].sum()):,} orders. "
        f"The strongest month is {peak_m} at {monthly.max():,.0f} BRL; "
        f"the weakest is {low_m} at {monthly.min():,.0f} BRL."
    )


def state_evidence(con, schema: str, source: str) -> str:
    df = con.execute(
        f"SELECT state, revenue, orders FROM {schema}.revenue_by_state "
        f"WHERE data_source = '{source}' ORDER BY revenue DESC"
    ).df()
    if df.empty:
        return "No state data."
    top = df.iloc[0]
    share = 100 * top["revenue"] / df["revenue"].sum()
    return (
        f"The top state is {top['state']} with {top['revenue']:,.0f} BRL "
        f"({share:.0f}% of total revenue) from {int(top['orders']):,} orders. "
        f"There are {len(df)} states with sales."
    )


def delivery_evidence(con, schema: str, source: str) -> str:
    df = con.execute(
        f"SELECT * FROM {schema}.delivery_performance WHERE data_source = '{source}'"
    ).df()
    if df.empty:
        return "No delivery data."
    r = df.iloc[0]
    return (
        f"Average delivery time is {r['avg_delivery_days']} days. "
        f"{int(r['late_orders']):,} of {int(r['delivered_orders']):,} orders were late, "
        f"a late rate of {r['late_rate_pct']}%."
    )


def review_evidence(con, schema: str, source: str) -> str:
    df = con.execute(
        f"SELECT review_score, reviews, pct_late FROM {schema}.review_analysis "
        f"WHERE data_source = '{source}' ORDER BY review_score"
    ).df()
    if df.empty:
        return "No review data."
    total = df["reviews"].sum()
    five = df[df["review_score"] == 5]["reviews"].sum()
    one = df[df["review_score"] == 1]
    five_pct = 100 * five / total
    parts = [f"Of {int(total):,} reviews, {five_pct:.0f}% are 5-star."]
    if not one.empty:
        parts.append(
            f"1-star reviews have a {one.iloc[0]['pct_late']}% late-delivery rate, "
            f"versus {df[df['review_score']==5]['pct_late'].iloc[0]}% for 5-star, "
            f"showing late delivery is associated with low scores."
        )
    return " ".join(parts)


def funnel_evidence(con, schema: str, source: str) -> str:
    df = con.execute(
        f"SELECT * FROM {schema}.funnel_conversion WHERE data_source = '{source}'"
    ).df()
    if df.empty:
        return "No funnel data."
    r = df.iloc[0]
    return (
        f"Of {int(r['purchased']):,} purchases, {int(r['delivered']):,} were delivered, "
        f"a delivery rate of {r['delivery_rate_pct']}%."
    )


def ab_evidence(con, schema: str) -> str:
    df = con.execute(f"SELECT * FROM {schema}.ab_test_results").df()
    if df.empty:
        return "No A/B data."
    lines = []
    for exp in df["ab_experiment"].unique():
        sub = df[df["ab_experiment"] == exp]
        a = sub[sub["ab_variant"] == "A"]["avg_order_value"]
        b = sub[sub["ab_variant"] == "B"]["avg_order_value"]
        if len(a) and len(b):
            lift = 100 * (b.iloc[0] - a.iloc[0]) / a.iloc[0]
            lines.append(f"{exp}: variant B AOV {b.iloc[0]:.0f} vs A {a.iloc[0]:.0f} BRL ({lift:+.1f}%).")
    return " ".join(lines) if lines else "No A/B data."


# Maps a chart key to (title, evidence builder). Source-scoped charts take a
# source; A/B is live-only.
CHART_BUILDERS = {
    "revenue": ("Monthly Revenue", revenue_evidence),
    "state": ("Revenue by State", state_evidence),
    "delivery": ("Delivery Performance", delivery_evidence),
    "review": ("Review Analysis", review_evidence),
    "funnel": ("Order Funnel", funnel_evidence),
}
