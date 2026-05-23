"""Tier 0 master generators: geolocation, categories, sellers, products.

These are generated once and are idempotent (written with replace=True).
Postcodes are read from a downloaded CSV if present; otherwise synthesized
from the state postcode ranges.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

from . import au_reference_data as ref
from . import realism_patterns as rp

POSTCODE_CSV = "data/raw/au_postcodes.csv"
N_GEOLOCATION = 2500
N_SELLERS = 500
N_PRODUCTS = 5000


def generate_geolocation(rng: np.random.Generator) -> pd.DataFrame:
    """Build the geolocation table from a CSV if available, else synthesize."""
    path = Path(POSTCODE_CSV)
    if path.exists():
        df = pd.read_csv(path, dtype={"postcode": str})
        df = df.sample(min(N_GEOLOCATION, len(df)), random_state=int(rng.integers(0, 1e6)))
        return pd.DataFrame(
            {
                "geolocation_postcode": df["postcode"].astype(str).str.zfill(4),
                "geolocation_lat": df.get("lat", pd.Series([np.nan] * len(df))),
                "geolocation_lng": df.get("lng", pd.Series([np.nan] * len(df))),
                "geolocation_city": df.get("city", pd.Series([""] * len(df))),
                "geolocation_state": df.get("state", pd.Series([""] * len(df))),
            }
        ).reset_index(drop=True)

    # Synthesize when no CSV present.
    rows = []
    for _ in range(N_GEOLOCATION):
        state = rp.sample_state(rng)
        city = rp.sample_city_for_state(rng, state)
        postcode = rp.sample_postcode_for_state(rng, state)
        # Rough AU bounding box for plausible lat/lng.
        lat = float(rng.uniform(-43.0, -10.0))
        lng = float(rng.uniform(113.0, 154.0))
        rows.append(
            {
                "geolocation_postcode": postcode,
                "geolocation_lat": round(lat, 6),
                "geolocation_lng": round(lng, 6),
                "geolocation_city": city,
                "geolocation_state": state,
            }
        )
    return pd.DataFrame(rows)


def generate_categories() -> pd.DataFrame:
    """Build the category translation table (identity mapping)."""
    return pd.DataFrame(
        {
            "product_category_name": ref.CATEGORIES,
            "product_category_name_english": ref.CATEGORIES,
        }
    )


def generate_sellers(rng: np.random.Generator, geo: pd.DataFrame) -> pd.DataFrame:
    """Build sellers, drawing postcode/city/state from geolocation."""
    fake = Faker()
    Faker.seed(int(rng.integers(0, 1e6)))
    idx = rng.integers(0, len(geo), size=N_SELLERS)
    sample = geo.iloc[idx].reset_index(drop=True)
    return pd.DataFrame(
        {
            "seller_id": [fake.uuid4() for _ in range(N_SELLERS)],
            "seller_postcode": sample["geolocation_postcode"].values,
            "seller_city": sample["geolocation_city"].values,
            "seller_state": sample["geolocation_state"].values,
        }
    )


def generate_products(rng: np.random.Generator) -> pd.DataFrame:
    """Build products, long-tail across categories with a base price."""
    fake = Faker()
    Faker.seed(int(rng.integers(0, 1e6)))
    cat_probs = rp.long_tail_weights(rng, len(ref.CATEGORIES), alpha=1.1)
    categories = rng.choice(ref.CATEGORIES, size=N_PRODUCTS, p=cat_probs)
    return pd.DataFrame(
        {
            "product_id": [fake.uuid4() for _ in range(N_PRODUCTS)],
            "product_category_name": categories,
            "product_weight_g": rng.integers(50, 30000, size=N_PRODUCTS),
            "product_length_cm": rng.integers(5, 100, size=N_PRODUCTS),
            "product_height_cm": rng.integers(2, 100, size=N_PRODUCTS),
            "product_width_cm": rng.integers(5, 100, size=N_PRODUCTS),
            "base_price": [rp.sample_price(rng) for _ in range(N_PRODUCTS)],
        }
    )


def generate_all_masters(seed: int | None = None) -> dict[str, pd.DataFrame]:
    """Generate all four master tables and return them keyed by table name."""
    rng = rp.make_rng(seed)
    geo = generate_geolocation(rng)
    return {
        "raw_geolocation": geo,
        "raw_category_translation": generate_categories(),
        "raw_sellers": generate_sellers(rng, geo),
        "raw_products": generate_products(rng),
    }
