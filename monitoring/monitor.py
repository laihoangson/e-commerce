"""Model monitoring and pipeline SLI/SLO checks.

Two concerns:

1. Model metrics - read the metrics each training run recorded in its artifact
   so they can be tracked over time and shown on the dashboard.

2. Service-level indicators (SLIs) measured against objectives (SLOs):
   - data freshness: how recent is the latest order?
   - validation pass rate: fraction of Bronze rows that passed Great Expectations
   - referential integrity: orphan rate in fact tables
   - gold completeness: are the expected Gold marts present and non-empty?

Each SLI is compared to an SLO threshold and reported as met / breached. This is
deliberately simple - the point is to demonstrate the monitoring discipline, not
to build a full observability stack.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class SLI:
    name: str
    value: float
    unit: str
    objective: str
    met: bool


def _scalar(con, sql: str):
    row = con.execute(sql).fetchone()
    return row[0] if row else None


def data_freshness(con) -> SLI:
    """Days since the most recent order. SLO: < 2 days (live mode keeps it fresh)."""
    latest = _scalar(
        con, "SELECT max(order_purchase_timestamp) FROM main_silver.fact_orders"
    )
    if latest is None:
        return SLI("data_freshness", 999, "days", "< 2 days", False)
    if isinstance(latest, str):
        latest = datetime.fromisoformat(latest)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    days = (now - latest.replace(tzinfo=None)).total_seconds() / 86400
    return SLI("data_freshness", round(days, 1), "days", "< 2 days", days < 2)


def validation_pass_rate(con) -> SLI:
    """Fraction of Bronze order rows marked valid. SLO: >= 99%."""
    total = _scalar(con, "SELECT count(*) FROM bronze.raw_orders") or 1
    valid = _scalar(
        con, "SELECT count(*) FROM bronze.raw_orders WHERE _is_valid IS NOT FALSE"
    ) or 0
    rate = 100.0 * valid / total
    return SLI("validation_pass_rate", round(rate, 2), "%", ">= 99%", rate >= 99.0)


def referential_integrity(con) -> SLI:
    """Orphan rate of order_items without a parent order. SLO: 0%."""
    total = _scalar(con, "SELECT count(*) FROM main_silver.fact_order_items") or 1
    orphans = _scalar(
        con,
        "SELECT count(*) FROM main_silver.fact_order_items i "
        "LEFT JOIN main_silver.fact_orders o USING(order_id) "
        "WHERE o.order_id IS NULL",
    ) or 0
    rate = 100.0 * orphans / total
    return SLI("referential_integrity_orphans", round(rate, 3), "%", "0%", orphans == 0)


def gold_completeness(con) -> SLI:
    """Fraction of expected Gold marts present and non-empty. SLO: 100%."""
    expected = [
        "daily_revenue", "customer_ltv", "cohort_retention", "seller_metrics",
        "ab_test_results", "funnel_conversion", "delivery_performance",
        "review_analysis", "revenue_by_state",
    ]
    present = 0
    for mart in expected:
        try:
            n = _scalar(con, f"SELECT count(*) FROM main_gold.{mart}")
            # ab_test_results may legitimately be empty if no experiments; count
            # presence rather than non-emptiness for that one.
            if n is not None and (n > 0 or mart == "ab_test_results"):
                present += 1
        except Exception:
            pass
    rate = 100.0 * present / len(expected)
    return SLI("gold_completeness", round(rate, 1), "%", "100%", present == len(expected))


def collect_slis(con) -> list[SLI]:
    return [
        data_freshness(con),
        validation_pass_rate(con),
        referential_integrity(con),
        gold_completeness(con),
    ]
