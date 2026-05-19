"""
pipeline/utils/faker_generator.py - Synthetic event generator for RetailLens.

Generates clickstream events that are consistent with Olist's customer_ids and
product_ids, so joins between real (Olist orders) and synthetic (clickstream)
data make semantic sense.

Two modes:
  - backfill: generates events with timestamps spanning 2016-2018, aligned
              with Olist's order timestamps. Run once during W2-W3 to seed
              historical data.
  - live:     generates events for "today" (the current pipeline run time).
              Run every cron (every 6h) to make the dashboard feel alive.

The 2-mode design is documented in docs/architecture.md (DD-3).
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from faker import Faker
from loguru import logger

# Make project root importable when run as script
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Event taxonomy - kept small to start, can expand in W3
EVENT_TYPES = [
    "page_view",
    "product_view",
    "add_to_cart",
    "remove_from_cart",
    "checkout_start",
    "checkout_complete",
    "search",
]

# Approximate funnel weights (page_view most common, checkout_complete rare)
EVENT_WEIGHTS = [0.40, 0.25, 0.12, 0.04, 0.08, 0.05, 0.06]

# Device + channel taxonomies
DEVICES = ["mobile", "desktop", "tablet"]
DEVICE_WEIGHTS = [0.62, 0.32, 0.06]

CHANNELS = ["organic", "paid_search", "social", "email", "direct", "referral"]
CHANNEL_WEIGHTS = [0.35, 0.20, 0.18, 0.12, 0.10, 0.05]


def _read_olist_ids_from_parquet(
    olist_dir: Path,
) -> tuple[list[str], list[str], pd.Series]:
    """
    Read customer_ids, product_ids, and order timestamps from Olist Parquet files.

    Returns:
        customer_ids: list of unique customer_unique_id values
        product_ids: list of unique product_id values
        order_dates: pandas Series of order_purchase_timestamp values (for backfill mode)
    """
    customers = pd.read_parquet(olist_dir / "olist_customers_dataset.parquet")
    products = pd.read_parquet(olist_dir / "olist_products_dataset.parquet")
    orders = pd.read_parquet(olist_dir / "olist_orders_dataset.parquet")

    customer_ids = customers["customer_unique_id"].unique().tolist()
    product_ids = products["product_id"].unique().tolist()

    # Convert timestamp column
    orders["order_purchase_timestamp"] = pd.to_datetime(
        orders["order_purchase_timestamp"]
    )
    order_dates = orders["order_purchase_timestamp"].dropna()

    logger.info(
        f"Olist universe loaded: {len(customer_ids):,} customers, "
        f"{len(product_ids):,} products, "
        f"{len(order_dates):,} order timestamps"
    )
    return customer_ids, product_ids, order_dates


def generate_clickstream(
    mode: str,
    olist_dir: Path,
    num_events: int,
    seed: int = 42,
    batch_id: str | None = None,
) -> pd.DataFrame:
    """
    Generate clickstream events.

    Args:
        mode: 'backfill' or 'live'
        olist_dir: directory with Olist Parquet files (for ID universe)
        num_events: how many events to generate
        seed: random seed for reproducibility
        batch_id: pipeline run identifier; auto-generated if None

    Returns:
        DataFrame with columns: event_id, event_type, customer_id, product_id,
        event_timestamp, device, channel, session_id, _ingested_at,
        _source_file, _batch_id, _is_valid
    """
    if mode not in ("backfill", "live"):
        raise ValueError(f"mode must be 'backfill' or 'live', got {mode!r}")

    rng = np.random.default_rng(seed)
    fake = Faker()
    Faker.seed(seed)

    customer_ids, product_ids, order_dates = _read_olist_ids_from_parquet(olist_dir)

    if batch_id is None:
        batch_id = str(uuid.uuid4())

    # --- Event timestamps ---
    if mode == "backfill":
        # Sample timestamps from Olist's order timestamp distribution.
        # This makes synthetic clickstream "match" real order pattern in time.
        sampled = order_dates.sample(n=num_events, replace=True, random_state=seed)
        # Shift each by random offset -7d to +1h to simulate browsing before purchase
        offsets_hours = rng.uniform(-168, 1, size=num_events)
        event_timestamps = sampled.values + pd.to_timedelta(offsets_hours, unit="h")
    else:
        # Live mode: events spread over last 6h (since last cron)
        now = datetime.now(timezone.utc)
        offsets_seconds = rng.uniform(-21600, 0, size=num_events)  # -6h to now
        event_timestamps = pd.Series(
            [now + timedelta(seconds=float(s)) for s in offsets_seconds]
        ).values

    # --- Sample IDs ---
    customer_sample = rng.choice(customer_ids, size=num_events)
    product_sample = rng.choice(product_ids, size=num_events)

    # --- Event types weighted ---
    event_type_sample = rng.choice(EVENT_TYPES, size=num_events, p=EVENT_WEIGHTS)

    # --- Device + channel ---
    devices = rng.choice(DEVICES, size=num_events, p=DEVICE_WEIGHTS)
    channels = rng.choice(CHANNELS, size=num_events, p=CHANNEL_WEIGHTS)

    # --- Sessions: 1 session = ~5 events from same customer in ~30min window ---
    # Simple approach: bucket events into sessions of 5 with a UUID each
    session_ids = []
    for i in range(num_events):
        if i % 5 == 0:
            current_session = str(uuid.uuid4())
        session_ids.append(current_session)

    df = pd.DataFrame({
        "event_id": [str(uuid.uuid4()) for _ in range(num_events)],
        "event_type": event_type_sample,
        "customer_id": customer_sample,
        "product_id": product_sample,
        "event_timestamp": pd.to_datetime(event_timestamps),
        "device": devices,
        "channel": channels,
        "session_id": session_ids,
    })

    # Bronze metadata columns
    ingested_at = datetime.now(timezone.utc)
    df["_ingested_at"] = ingested_at
    df["_source_file"] = f"faker:clickstream:{mode}"
    df["_batch_id"] = batch_id
    df["_is_valid"] = True  # W2 default; W3 GE will overwrite

    logger.success(
        f"Generated {len(df):,} clickstream events ({mode} mode, batch {batch_id[:8]}...)"
    )
    return df


def write_to_duckdb(
    df: pd.DataFrame,
    duckdb_path: Path,
    table: str = "bronze.raw_clickstream",
    if_exists: str = "append",
) -> None:
    """Write clickstream DataFrame to DuckDB bronze schema."""
    schema, table_name = table.split(".")
    con = duckdb.connect(str(duckdb_path))
    try:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

        # Register DataFrame as a temporary view
        con.register("clickstream_tmp", df)

        if if_exists == "replace":
            con.execute(f"DROP TABLE IF EXISTS {table}")

        # Create or append - use CREATE TABLE IF NOT EXISTS, then INSERT
        con.execute(f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM clickstream_tmp WHERE 1=0")
        con.execute(f"INSERT INTO {table} SELECT * FROM clickstream_tmp")

        count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        logger.success(f"Wrote {len(df):,} rows to {table} (total now: {count:,})")
    finally:
        con.close()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["backfill", "live"], required=True)
    parser.add_argument(
        "--num-events", type=int, default=50000,
        help="How many events to generate (default 50000 backfill, 2000 live recommended)",
    )
    parser.add_argument(
        "--olist-dir", type=Path, default=Path("data/raw/olist"),
        help="Directory containing Olist Parquet files",
    )
    parser.add_argument(
        "--duckdb-path", type=Path, default=Path("data/retaillens.duckdb"),
        help="DuckDB file path",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Generate but don't write to DuckDB (print head only)",
    )
    args = parser.parse_args()

    df = generate_clickstream(
        mode=args.mode,
        olist_dir=args.olist_dir,
        num_events=args.num_events,
        seed=args.seed,
    )

    if args.dry_run:
        print(df.head(10))
        print(f"\nTotal: {len(df):,} rows, {df.memory_usage(deep=True).sum()/1024/1024:.1f} MB")
    else:
        write_to_duckdb(df, args.duckdb_path)