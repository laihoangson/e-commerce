"""Distribution samplers calibrated to the Olist reference patterns.

Centralizes the randomness so every generator draws from the same calibrated
distributions. See docs/reference/olist-calibration-reference.md.
"""

from __future__ import annotations

import numpy as np

from . import au_reference_data as ref


def make_rng(seed: int | None = None) -> np.random.Generator:
    """Create a numpy random Generator (reproducible if seed given)."""
    return np.random.default_rng(seed)


def weighted_choice(rng: np.random.Generator, weights: dict[str, float]) -> str:
    """Pick a key from a {label: weight} dict, proportional to weight."""
    labels = list(weights.keys())
    probs = np.array(list(weights.values()), dtype=float)
    probs = probs / probs.sum()
    return str(rng.choice(labels, p=probs))


def sample_state(rng: np.random.Generator) -> str:
    """Sample a state by population weight."""
    return weighted_choice(rng, ref.STATES)


def sample_city_for_state(rng: np.random.Generator, state: str) -> str:
    """Sample a city belonging to the given state (fallback: any city)."""
    cities = ref.STATE_CITIES.get(state)
    if not cities:
        cities = list(ref.CITY_STATE.keys())
    return str(rng.choice(cities))


def sample_postcode_for_state(rng: np.random.Generator, state: str) -> str:
    """Sample a 4-digit postcode within the state's allowed ranges."""
    ranges = ref.POSTCODE_RANGES.get(state, [(2000, 2999)])
    lo, hi = ranges[rng.integers(0, len(ranges))]
    code = int(rng.integers(lo, hi + 1))
    return f"{code:04d}"


def sample_price(rng: np.random.Generator) -> float:
    """Log-normal unit price, median ~A$90, long right tail. Min A$5."""
    # exp(mean) ~= 90 -> mean ~= ln(90) ~= 4.5; sigma controls tail width.
    value = float(rng.lognormal(mean=4.5, sigma=0.7))
    return round(max(5.0, value), 2)


def sample_freight(rng: np.random.Generator, price: float) -> float:
    """Freight as 8-22% of price plus a small fixed floor."""
    pct = float(rng.uniform(0.08, 0.22))
    return round(max(4.99, price * pct), 2)


def sample_item_count(rng: np.random.Generator) -> int:
    """Number of items in an order. ~88% single-item, decaying tail to 5."""
    r = float(rng.random())
    if r < 0.88:
        return 1
    if r < 0.96:
        return 2
    if r < 0.99:
        return 3
    return int(rng.integers(4, 6))


def sample_review_score(rng: np.random.Generator, is_late: bool) -> int:
    """Review score 1-5, conditional on whether delivery was late."""
    weights = (
        ref.REVIEW_SCORE_WEIGHTS_LATE if is_late else ref.REVIEW_SCORE_WEIGHTS_ONTIME
    )
    probs = np.array(weights, dtype=float)
    probs = probs / probs.sum()
    return int(rng.choice([1, 2, 3, 4, 5], p=probs))


def sample_installments(rng: np.random.Generator, payment_type: str) -> int:
    """Installment count based on the payment type's installment mode."""
    _, mode = ref.PAYMENT_TYPES[payment_type]
    if mode == "credit":
        # Skew toward 1-4 installments.
        r = float(rng.random())
        if r < 0.55:
            return int(rng.integers(1, 5))
        if r < 0.85:
            return int(rng.integers(5, 11))
        return int(rng.integers(11, 25))
    if mode == "fixed4":
        return 4
    return 1


def dow_multiplier(weekday: int) -> float:
    """Day-of-week order-volume multiplier (Mon=0 .. Sun=6)."""
    return ref.DOW_MULTIPLIERS[weekday % 7]


def is_late_delivery(rng: np.random.Generator) -> bool:
    """~8% of delivered orders are late."""
    return bool(rng.random() < 0.08)


def long_tail_weights(rng: np.random.Generator, n: int, alpha: float = 1.4) -> np.ndarray:
    """Generate normalized long-tail (Zipf-like) weights for n entities."""
    ranks = np.arange(1, n + 1)
    raw = 1.0 / np.power(ranks, alpha)
    rng.shuffle(raw)
    return raw / raw.sum()
