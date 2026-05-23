"""Tier 1 customer generator.

Produces one customer row per order. ~5% of customers are repeaters, modeled
with a stable customer_unique_id shared across their orders. A pool of unique
customers is built first, then sampled (with repetition) to the order count.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from faker import Faker

from . import realism_patterns as rp

REPEAT_RATE = 0.05


def generate_customers(
    n_orders: int,
    geo: pd.DataFrame,
    seed: int | None = None,
) -> pd.DataFrame:
    """Generate n_orders customer rows (one per order).

    Args:
        n_orders: number of order-level customer rows to produce.
        geo: geolocation table to draw location from.
        seed: optional reproducibility seed.

    Returns:
        DataFrame with one row per order, including a stable customer_unique_id.
    """
    rng = rp.make_rng(seed)
    fake = Faker()
    Faker.seed(int(rng.integers(0, 1e6)))

    # Size the unique-customer pool so that ~REPEAT_RATE of customers repeat.
    # If r fraction repeat (avg ~2 orders each), pool size p satisfies:
    # n_orders ~= p * (1 + REPEAT_RATE)  ->  p ~= n_orders / (1 + REPEAT_RATE)
    pool_size = int(n_orders / (1.0 + REPEAT_RATE))
    unique_ids = [fake.uuid4() for _ in range(pool_size)]

    # Assign each pool customer a home location.
    geo_idx = rng.integers(0, len(geo), size=pool_size)
    geo_sample = geo.iloc[geo_idx].reset_index(drop=True)
    pool = pd.DataFrame(
        {
            "customer_unique_id": unique_ids,
            "customer_postcode": geo_sample["geolocation_postcode"].values,
            "customer_city": geo_sample["geolocation_city"].values,
            "customer_state": geo_sample["geolocation_state"].values,
        }
    )

    # Sample pool members to fill n_orders. A small repeat set is sampled twice+.
    n_repeaters = int(pool_size * REPEAT_RATE)
    repeater_idx = rng.choice(pool_size, size=n_repeaters, replace=False)

    order_pool_idx = list(range(pool_size))  # each customer at least once
    remaining = n_orders - pool_size
    if remaining > 0:
        extra = rng.choice(repeater_idx, size=remaining, replace=True)
        order_pool_idx.extend(extra.tolist())
    rng.shuffle(order_pool_idx)
    order_pool_idx = order_pool_idx[:n_orders]

    chosen = pool.iloc[order_pool_idx].reset_index(drop=True)
    chosen.insert(0, "customer_id", [fake.uuid4() for _ in range(len(chosen))])
    return chosen
