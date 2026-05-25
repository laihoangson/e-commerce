"""Faker live tail generator.

Continues the Olist timeline with a small synthetic stream (default 2024-2026,
~20 orders/day) so the dashboard feels live. Reuses the real Olist pools
(products, sellers, customers) rather than inventing new master data.

Design decisions:
  - ~40% of live orders are placed by existing Olist customers (reusing their
    customer_unique_id), creating a repeat-purchase bridge; ~60% are new
    customers.
  - Orders carry A/B experiment assignments. One experiment (welcome_voucher)
    has a real, deliberate effect on order value so the A/B engine can detect a
    significant result; the other (free_shipping_threshold) is a null effect.
  - Rows are tagged _data_source = 'faker_live' to distinguish them from Olist.

This is documented synthetic data by design, not a claim of real transactions.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from faker import Faker

load_dotenv()

from utils.bronze_writer import write_bronze  # noqa: E402
from utils.duckdb_client import get_connection, table_exists  # noqa: E402
from utils import realism_patterns as rp  # noqa: E402

LIVE_START = "2024-01-01"
LIVE_END = "2026-05-25"
ORDERS_PER_DAY = 20
EXISTING_CUSTOMER_RATE = 0.40
SEED = 11

# Brazilian payment types (match Olist).
PAYMENT_WEIGHTS = {
    "credit_card": 0.74,
    "boleto": 0.19,
    "voucher": 0.05,
    "debit_card": 0.02,
}

# A/B experiments. welcome_voucher carries a real AOV uplift for variant B.
AB_EXPERIMENTS = {
    "free_shipping_threshold": {"effect": 0.0},   # null effect (control)
    "welcome_voucher": {"effect": 0.15},          # +15% AOV for variant B
}


def _load_pools(con):
    products = con.execute(
        "SELECT product_id FROM bronze.raw_products WHERE _is_valid IS NOT FALSE"
    ).df()["product_id"].values
    sellers = con.execute("SELECT seller_id FROM bronze.raw_sellers").df()[
        "seller_id"
    ].values
    existing = con.execute(
        "SELECT DISTINCT customer_unique_id, customer_postcode, customer_city, "
        "customer_state FROM bronze.raw_customers"
    ).df()
    # A rough product price reference from real Olist item prices.
    price_ref = con.execute(
        "SELECT product_id, avg(price) AS p FROM bronze.raw_order_items "
        "GROUP BY product_id"
    ).df()
    price_map = dict(zip(price_ref["product_id"], price_ref["p"]))
    return products, sellers, existing, price_map


def generate_live(con, seed: int = SEED) -> dict[str, pd.DataFrame]:
    rng = rp.make_rng(seed)
    fake = Faker("pt_BR")
    Faker.seed(seed)

    products, sellers, existing, price_map = _load_pools(con)
    existing_idx = np.arange(len(existing))

    start = datetime.fromisoformat(LIVE_START)
    end = datetime.fromisoformat(LIVE_END)

    orders, items, payments, reviews, customers = [], [], [], [], []
    seen_customers = set()

    # Fixed pool of "new" live customers, each with a hidden loyalty propensity.
    # High-propensity customers are sampled more often (producing repeat
    # purchases) AND tend to leave higher review scores, creating a realistic,
    # NOISY correlation between observable features (recency, frequency, review)
    # and future repurchase. This lets the reactivation model learn signal
    # without it being trivial. Synthetic by design; documented as such.
    n_pool = 6000
    pool_ids = [fake.uuid4() for _ in range(n_pool)]
    propensity = rng.beta(1.5, 6.0, size=n_pool)  # skewed low (mostly one-and-done)
    pool_states = rng.choice(["SP", "RJ", "MG", "RS", "PR", "SC", "BA"], size=n_pool)
    pool_cities = [fake.city() for _ in range(n_pool)]
    pool_postcodes = rng.integers(1000, 99999, size=n_pool)
    pool_weights = (0.2 + propensity) / (0.2 + propensity).sum()

    day = start
    while day <= end:
        mult = rp.dow_multiplier(day.weekday())
        n = max(0, int(round(ORDERS_PER_DAY * mult * float(rng.normal(1.0, 0.1)))))
        for _ in range(n):
            order_id = fake.uuid4()
            cust_propensity = 0.0
            # customer: 40% existing Olist customer, 60% from the live pool
            if rng.random() < EXISTING_CUSTOMER_RATE and len(existing) > 0:
                row = existing.iloc[int(rng.choice(existing_idx))]
                cust_unique = row["customer_unique_id"]
                postcode, city, state = (
                    row["customer_postcode"], row["customer_city"], row["customer_state"]
                )
            else:
                pi = int(rng.choice(n_pool, p=pool_weights))
                cust_unique = pool_ids[pi]
                cust_propensity = float(propensity[pi])
                state = str(pool_states[pi])
                city = pool_cities[pi]
                postcode = str(int(pool_postcodes[pi]))
            customer_id = fake.uuid4()  # per-order id, like Olist
            customers.append({
                "customer_id": customer_id,
                "customer_unique_id": cust_unique,
                "customer_postcode": str(postcode),
                "customer_city": city,
                "customer_state": state,
            })

            # A/B assignment (most live orders are in an experiment)
            experiment = None
            variant = None
            ab_mult = 1.0
            if rng.random() < 0.6:
                experiment = str(rng.choice(list(AB_EXPERIMENTS.keys())))
                variant = "A" if rng.random() < 0.5 else "B"
                if variant == "B":
                    ab_mult = 1.0 + AB_EXPERIMENTS[experiment]["effect"]

            purchase = day + timedelta(
                hours=int(rng.integers(0, 24)), minutes=int(rng.integers(0, 60))
            )
            approved = purchase + timedelta(hours=float(rng.uniform(0.2, 24)))
            estimated = purchase + timedelta(days=float(rng.uniform(5, 18)))
            carrier = approved + timedelta(days=float(rng.uniform(0.5, 4)))
            late = rp.is_late_delivery(rng)
            if late:
                delivered = estimated + timedelta(days=float(rng.uniform(1, 7)))
            else:
                earliest = carrier + timedelta(hours=12)
                if earliest >= estimated:
                    delivered = estimated - timedelta(hours=float(rng.uniform(2, 24)))
                else:
                    span = (estimated - earliest).total_seconds()
                    delivered = earliest + timedelta(seconds=float(rng.uniform(0, span * 0.9)))

            orders.append({
                "order_id": order_id,
                "customer_id": customer_id,
                "order_status": "delivered",
                "order_purchase_timestamp": purchase,
                "order_approved_at": approved,
                "order_delivered_carrier_date": carrier,
                "order_delivered_customer_date": delivered,
                "order_estimated_delivery_date": estimated,
                "ab_experiment": experiment,
                "ab_variant": variant,
            })

            # items
            n_items = rp.sample_item_count(rng)
            for seq in range(1, n_items + 1):
                pid = str(rng.choice(products))
                base = price_map.get(pid)
                base = float(base) if base and base > 0 else rp.sample_price(rng)
                price = round(base * float(rng.uniform(0.85, 1.15)) * ab_mult, 2)
                freight = rp.sample_freight(rng, price)
                items.append({
                    "order_id": order_id,
                    "order_item_id": seq,
                    "product_id": pid,
                    "seller_id": str(rng.choice(sellers)),
                    "price": price,
                    "freight_value": freight,
                })

            # payment
            ptype = rp.weighted_choice(rng, PAYMENT_WEIGHTS)
            inst = int(rng.integers(1, 13)) if ptype == "credit_card" else 1
            order_total = sum(
                i["price"] + i["freight_value"] for i in items if i["order_id"] == order_id
            )
            payments.append({
                "order_id": order_id,
                "payment_sequential": 1,
                "payment_type": ptype,
                "payment_installments": inst,
                "payment_value": round(order_total, 2),
            })

            # review (~99% of delivered)
            if rng.random() < 0.99:
                is_late = delivered > estimated
                score = rp.sample_review_score(rng, is_late)
                # High-propensity (loyal) customers tend to rate higher; bump
                # their score up with some probability proportional to propensity.
                if cust_propensity > 0 and rng.random() < cust_propensity:
                    score = min(5, score + 1)
                reviews.append({
                    "review_id": fake.uuid4(),
                    "order_id": order_id,
                    "review_score": score,
                    "review_comment_title": None,
                    "review_comment_message": None,
                    "review_creation_date": delivered + timedelta(days=float(rng.uniform(1, 10))),
                })
        day += timedelta(days=1)

    return {
        "raw_customers": pd.DataFrame(customers),
        "raw_orders": pd.DataFrame(orders),
        "raw_order_items": pd.DataFrame(items),
        "raw_payments": pd.DataFrame(payments),
        "raw_reviews": pd.DataFrame(reviews),
    }


def main() -> int:
    batch = f"faker-live-{uuid.uuid4().hex[:8]}"
    print("=" * 56)
    print(f"Faker live tail: {LIVE_START} .. {LIVE_END} (~{ORDERS_PER_DAY}/day)")
    print(f"batch {batch}")
    print("=" * 56)

    con = get_connection()
    if not table_exists(con, "bronze", "raw_orders"):
        print("[FAIL] Olist Bronze not found. Run pipeline/load_olist_bronze.py first.")
        con.close()
        return 1

    tables = generate_live(con)
    for table, df in tables.items():
        df["_data_source"] = "faker_live"
        # append to the existing Olist tables
        n = write_bronze(con, df, table, "live_generator", batch, replace=False)
        print(f"  [OK] appended {n} rows to bronze.{table}")

    con.close()
    print("Live tail appended.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
