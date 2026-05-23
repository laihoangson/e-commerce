"""Tier 2 transactional generator: orders, items, payments, reviews.

Emits the four transactional tables together so foreign keys stay consistent.
Each order gets lifecycle timestamps, an optional A/B experiment assignment, and
a small fraction of rows are deliberately corrupted for the Great Expectations
demo in Phase 3.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from faker import Faker

from . import au_reference_data as ref
from . import realism_patterns as rp

DIRTY_RATE = 0.015  # fraction of orders given a data-quality defect
AB_ASSIGN_RATE = 0.30  # fraction of orders assigned to an experiment


def _daily_order_counts(
    rng: np.random.Generator, start: datetime, end: datetime, base_per_day: int
) -> list[tuple[datetime, int]]:
    """Compute per-day order counts with day-of-week seasonality."""
    days = []
    cur = start
    while cur <= end:
        mult = rp.dow_multiplier(cur.weekday())
        noise = float(rng.normal(1.0, 0.08))
        count = max(0, int(round(base_per_day * mult * noise)))
        days.append((cur, count))
        cur += timedelta(days=1)
    return days


def _lifecycle_timestamps(
    rng: np.random.Generator, purchase: datetime, status: str
) -> dict[str, datetime | None]:
    """Produce the five lifecycle timestamps, strictly ordered when present."""
    approved = purchase + timedelta(hours=float(rng.uniform(0.2, 24)))
    estimated = purchase + timedelta(days=float(rng.uniform(5, 18)))

    carrier = None
    delivered = None
    if status in ("delivered", "shipped"):
        carrier = approved + timedelta(days=float(rng.uniform(0.5, 4)))
    if status == "delivered":
        late = rp.is_late_delivery(rng)
        if late:
            delivered = estimated + timedelta(days=float(rng.uniform(1, 7)))
        else:
            # On-time: deliver after carrier handoff but strictly before the
            # estimate, so the late rate stays ~8% rather than leaking upward.
            earliest = carrier + timedelta(hours=12)
            if earliest >= estimated:
                delivered = estimated - timedelta(hours=float(rng.uniform(2, 24)))
            else:
                span = (estimated - earliest).total_seconds()
                delivered = earliest + timedelta(
                    seconds=float(rng.uniform(0, span * 0.9))
                )

    return {
        "order_approved_at": approved,
        "order_delivered_carrier_date": carrier,
        "order_delivered_customer_date": delivered,
        "order_estimated_delivery_date": estimated,
    }


def _assign_ab(rng: np.random.Generator) -> tuple[str | None, str | None]:
    """Optionally assign an order to an A/B experiment + variant."""
    if rng.random() >= AB_ASSIGN_RATE:
        return None, None
    experiment = str(rng.choice(list(ref.AB_EXPERIMENTS.keys())))
    variant = "A" if rng.random() < 0.5 else "B"
    return experiment, variant


def generate_transactional(
    customers: pd.DataFrame,
    products: pd.DataFrame,
    sellers: pd.DataFrame,
    start_date: str,
    end_date: str,
    base_per_day: int = 100,
    seed: int | None = None,
) -> dict[str, pd.DataFrame]:
    """Generate orders, items, payments, reviews for a date window.

    The number of orders is driven by the date window and base_per_day, not by
    len(customers); customers are sampled to match the generated order count.

    Returns:
        Dict keyed by table name -> DataFrame.
    """
    rng = rp.make_rng(seed)
    fake = Faker()
    Faker.seed(int(rng.integers(0, 1e6)))

    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    day_counts = _daily_order_counts(rng, start, end, base_per_day)
    total_orders = sum(c for _, c in day_counts)

    # Align customer rows to the order count (resample if mismatched).
    if len(customers) >= total_orders:
        cust = customers.iloc[:total_orders].reset_index(drop=True)
    else:
        extra_idx = rng.integers(0, len(customers), size=total_orders - len(customers))
        cust = pd.concat(
            [customers, customers.iloc[extra_idx]], ignore_index=True
        ).iloc[:total_orders].reset_index(drop=True)

    product_ids = products["product_id"].values
    product_prices = dict(zip(products["product_id"], products["base_price"]))
    seller_ids = sellers["seller_id"].values

    orders, items, payments, reviews = [], [], [], []
    statuses = list(ref.ORDER_STATUS_WEIGHTS.keys())
    status_probs = np.array(list(ref.ORDER_STATUS_WEIGHTS.values()))
    status_probs = status_probs / status_probs.sum()

    order_cursor = 0
    for day, count in day_counts:
        for _ in range(count):
            if order_cursor >= total_orders:
                break
            order_id = fake.uuid4()
            customer_id = cust.iloc[order_cursor]["customer_id"]
            order_cursor += 1

            status = str(rng.choice(statuses, p=status_probs))
            purchase = day + timedelta(
                hours=int(rng.integers(0, 24)), minutes=int(rng.integers(0, 60))
            )
            ts = _lifecycle_timestamps(rng, purchase, status)
            experiment, variant = _assign_ab(rng)
            is_dirty = rng.random() < DIRTY_RATE

            # Dirty defect type 1: impossible lifecycle ordering.
            if is_dirty and status == "delivered" and ts["order_delivered_customer_date"]:
                ts["order_delivered_customer_date"] = purchase - timedelta(days=1)

            orders.append(
                {
                    "order_id": order_id,
                    "customer_id": customer_id,
                    "order_status": status,
                    "order_purchase_timestamp": purchase,
                    **ts,
                    "ab_experiment": experiment,
                    "ab_variant": variant,
                }
            )

            # Items.
            n_items = rp.sample_item_count(rng)
            order_total = 0.0
            for item_seq in range(1, n_items + 1):
                pid = str(rng.choice(product_ids))
                base = product_prices.get(pid, rp.sample_price(rng))
                price = round(float(base) * float(rng.uniform(0.85, 1.15)), 2)
                if is_dirty and item_seq == 1 and rng.random() < 0.5:
                    price = -price  # dirty defect type 2: negative price
                freight = rp.sample_freight(rng, abs(price))
                order_total += abs(price) + freight
                items.append(
                    {
                        "order_id": order_id,
                        "order_item_id": item_seq,
                        "product_id": pid,
                        "seller_id": str(rng.choice(seller_ids)),
                        "price": price,
                        "freight_value": freight,
                    }
                )

            # Payment (99% single).
            ptype = rp.weighted_choice(
                rng, {k: v[0] for k, v in ref.PAYMENT_TYPES.items()}
            )
            installments = rp.sample_installments(rng, ptype)
            if is_dirty and rng.random() < 0.4 and ptype != "credit_card":
                installments = int(rng.integers(2, 12))  # dirty: installments on non-credit
            payments.append(
                {
                    "order_id": order_id,
                    "payment_sequential": 1,
                    "payment_type": ptype,
                    "payment_installments": installments,
                    "payment_value": round(order_total, 2),
                }
            )

            # Review (only for delivered orders, ~99% coverage).
            if status == "delivered" and rng.random() < 0.99:
                is_late = (
                    ts["order_delivered_customer_date"] is not None
                    and ts["order_delivered_customer_date"]
                    > ts["order_estimated_delivery_date"]
                )
                score = rp.sample_review_score(rng, bool(is_late))
                review_dt = (ts["order_delivered_customer_date"] or purchase) + timedelta(
                    days=float(rng.uniform(1, 10))
                )
                reviews.append(
                    {
                        "review_id": fake.uuid4(),
                        "order_id": order_id,
                        "review_score": score,
                        "review_comment_title": (
                            fake.sentence(nb_words=4) if rng.random() < 0.3 else None
                        ),
                        "review_comment_message": (
                            fake.sentence(nb_words=12) if rng.random() < 0.4 else None
                        ),
                        "review_creation_date": review_dt,
                    }
                )

    return {
        "raw_orders": pd.DataFrame(orders),
        "raw_order_items": pd.DataFrame(items),
        "raw_payments": pd.DataFrame(payments),
        "raw_reviews": pd.DataFrame(reviews),
    }
