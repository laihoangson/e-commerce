"""Australian context constants for the Faker generators.

Single source of truth for AU-specific values. Mirrors docs/au-entities.md.
"""

from __future__ import annotations

# States sampled by approximate population weight (weights sum to 1.0).
STATES: dict[str, float] = {
    "NSW": 0.32,
    "VIC": 0.26,
    "QLD": 0.20,
    "WA": 0.11,
    "SA": 0.07,
    "TAS": 0.02,
    "ACT": 0.015,
    "NT": 0.005,
}

# City -> primary state. City is sampled conditional on the chosen state.
CITY_STATE: dict[str, str] = {
    "Sydney": "NSW",
    "Newcastle": "NSW",
    "Melbourne": "VIC",
    "Brisbane": "QLD",
    "Gold Coast": "QLD",
    "Perth": "WA",
    "Adelaide": "SA",
    "Hobart": "TAS",
    "Canberra": "ACT",
    "Darwin": "NT",
}

# Inverse lookup: state -> list of its cities.
STATE_CITIES: dict[str, list[str]] = {}
for _city, _state in CITY_STATE.items():
    STATE_CITIES.setdefault(_state, []).append(_city)

# Payment types: (weight, installment_mode).
# installment_mode: "credit" = 1..24, "fixed4" = always 4, "single" = always 1.
PAYMENT_TYPES: dict[str, tuple[float, str]] = {
    "credit_card": (0.45, "credit"),
    "debit_card": (0.25, "single"),
    "afterpay": (0.15, "fixed4"),
    "bpay": (0.10, "single"),
    "paypal": (0.05, "single"),
}

# Postcode prefix ranges per state (inclusive), 4-digit AU format.
POSTCODE_RANGES: dict[str, list[tuple[int, int]]] = {
    "NSW": [(2000, 2599), (2619, 2899), (2921, 2999)],
    "ACT": [(2600, 2618), (2900, 2920)],
    "VIC": [(3000, 3999)],
    "QLD": [(4000, 4999)],
    "SA": [(5000, 5799)],
    "WA": [(6000, 6797)],
    "TAS": [(7000, 7799)],
    "NT": [(800, 899)],
}

# 30 Australian-flavoured product categories.
CATEGORIES: list[str] = [
    "outdoor_furniture",
    "skincare",
    "electronics",
    "sportswear",
    "homewares",
    "kids_toys",
    "books",
    "home_office",
    "beauty_haircare",
    "pet_supplies",
    "kitchen_dining",
    "garden_outdoor",
    "fashion_womens",
    "fashion_mens",
    "fashion_kids",
    "baby_nursery",
    "automotive",
    "food_grocery",
    "health_wellness",
    "fitness_equipment",
    "jewelry",
    "watches",
    "music_instruments",
    "gaming",
    "computers",
    "mobile_phones",
    "cameras_photo",
    "art_craft",
    "party_supplies",
    "australian_made",
]

CURRENCY = "AUD"

# Day-of-week order-volume multipliers (Mon=0 .. Sun=6). Mon-Tue peak.
DOW_MULTIPLIERS: list[float] = [1.15, 1.15, 1.05, 1.0, 0.95, 0.85, 0.85]

# Review score distribution for on-time deliveries (scores 1..5).
REVIEW_SCORE_WEIGHTS_ONTIME: list[float] = [0.08, 0.07, 0.08, 0.19, 0.58]
# Shifted toward low scores for late deliveries.
REVIEW_SCORE_WEIGHTS_LATE: list[float] = [0.35, 0.25, 0.18, 0.12, 0.10]

# Order status distribution.
ORDER_STATUS_WEIGHTS: dict[str, float] = {
    "delivered": 0.97,
    "shipped": 0.015,
    "canceled": 0.008,
    "unavailable": 0.004,
    "processing": 0.003,
}

# A/B experiments: name -> (variant_a_label, variant_b_label).
AB_EXPERIMENTS: dict[str, tuple[str, str]] = {
    "free_shipping_threshold": ("A$50", "A$100"),
    "welcome_voucher": ("10%", "20%"),
}
