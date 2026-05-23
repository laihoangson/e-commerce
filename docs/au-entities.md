# Australian Context Entities

Reference for all Australia-specific constants used by the Faker generators.
These values define the "shape" of RetailLens synthetic data and are the single
source of truth — generators import them from `pipeline/utils/au_reference_data.py`,
which mirrors this document.

## States and territories

Sampled by approximate population weight (not uniform). Weights sum to 1.0.

| Code | Name | Weight |
|------|------|--------|
| NSW | New South Wales | 0.32 |
| VIC | Victoria | 0.26 |
| QLD | Queensland | 0.20 |
| WA | Western Australia | 0.11 |
| SA | South Australia | 0.07 |
| TAS | Tasmania | 0.02 |
| ACT | Australian Capital Territory | 0.015 |
| NT | Northern Territory | 0.005 |

## Cities

Each city maps to a primary state. Customer city is sampled conditional on the
sampled state so geography stays internally consistent.

| City | State |
|------|-------|
| Sydney | NSW |
| Newcastle | NSW |
| Melbourne | VIC |
| Brisbane | QLD |
| Gold Coast | QLD |
| Perth | WA |
| Adelaide | SA |
| Hobart | TAS |
| Canberra | ACT |
| Darwin | NT |

## Payment types

Sampled by weight. `credit_card` supports installments (1–24); all others are
single payment.

| Type | Weight | Installments |
|------|--------|--------------|
| credit_card | 0.45 | 1–24 |
| debit_card | 0.25 | 1 |
| afterpay | 0.15 | 4 (fixed) |
| bpay | 0.10 | 1 |
| paypal | 0.05 | 1 |

## Currency

All monetary values are in AUD. Prices follow a log-normal distribution
(see olist-calibration-reference.md).

## Postcodes

4-digit Australian format. Real postcode + lat/lng data is downloaded from the
Matthew Proctor community postcode database and sampled to ~2,500 rows for the
`raw_geolocation` table. State prefix ranges follow the Australian standard:

| State | Postcode range |
|-------|----------------|
| NSW | 2000–2999 |
| ACT | 2600–2618, 2900–2920 |
| VIC | 3000–3999 |
| QLD | 4000–4999 |
| SA | 5000–5799 |
| WA | 6000–6797 |
| TAS | 7000–7799 |
| NT | 0800–0899 |

## Product categories (30)

Australian-flavoured categories (not the Brazilian Olist categories). Products
are distributed long-tail across these.

outdoor_furniture, skincare, electronics, sportswear, homewares, kids_toys,
books, home_office, beauty_haircare, pet_supplies, kitchen_dining,
garden_outdoor, fashion_womens, fashion_mens, fashion_kids, baby_nursery,
automotive, food_grocery, health_wellness, fitness_equipment, jewelry, watches,
music_instruments, gaming, computers, mobile_phones, cameras_photo, art_craft,
party_supplies, australian_made
