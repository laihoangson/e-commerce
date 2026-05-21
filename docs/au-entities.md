# Australian e-commerce entities reference

## Purpose

This document is the single source of truth for all Australian context constants used in Faker generators. Code in `pipeline/utils/au_reference_data.py` should mirror these lists.

## States and territories

Australia has 6 states and 2 territories. Population shares as of 2024:

| Code | Name | Population share | Notes |
|------|------|------------------|-------|
| NSW | New South Wales | 32.0% | Includes Sydney |
| VIC | Victoria | 26.0% | Includes Melbourne |
| QLD | Queensland | 20.0% | Includes Brisbane, Gold Coast |
| WA | Western Australia | 11.0% | Includes Perth |
| SA | South Australia | 7.0% | Includes Adelaide |
| TAS | Tasmania | 2.0% | Includes Hobart |
| ACT | Australian Capital Territory | 1.5% | Includes Canberra |
| NT | Northern Territory | 0.5% | Includes Darwin |

Weights used for sampling customer states. Sellers follow slightly different distribution (more concentrated in NSW/VIC) reflecting wholesale concentration.

## Cities

Top 8 cities by metro population:

| City | State | Postcode prefix range |
|------|-------|----------------------|
| Sydney | NSW | 2000-2249 |
| Melbourne | VIC | 3000-3207 |
| Brisbane | QLD | 4000-4179 |
| Perth | WA | 6000-6175 |
| Adelaide | SA | 5000-5199 |
| Gold Coast | QLD | 4207-4230 |
| Newcastle | NSW | 2280-2308 |
| Canberra | ACT | 2600-2620 |

Additional cities for coverage: Hobart (TAS, 7000-7099), Darwin (NT, 0800-0899), Geelong (VIC, 3214-3220), Cairns (QLD, 4870-4879), Wollongong (NSW, 2500-2530).

## Payment types

5 payment types reflecting Australian e-commerce reality:

| Type | Weight | Description |
|------|--------|-------------|
| credit_card | 45% | Visa/Mastercard, supports installments 1-24 |
| debit_card | 25% | EFTPOS-linked debit |
| afterpay | 15% | BNPL provider, fixed 4 installments |
| bpay | 10% | Bank-issued biller code payment |
| paypal | 5% | PayPal Express checkout |

Notes:
- Afterpay is Australian fintech pride point; expect recruiter to recognize
- BPAY is unique to Australia (bank-to-bank payment with biller code)
- Stripe + Square not in list because they're processors, not consumer-facing payment types
- Cash on delivery omitted; e-commerce only

## Product categories

30 categories tailored to Australian e-commerce market:

```
outdoor_furniture
skincare
electronics
sportswear
homewares
kids_toys
books
home_office
beauty_haircare
pet_supplies
kitchen_dining
garden_outdoor
fashion_womens
fashion_mens
fashion_kids
baby_nursery
automotive
food_grocery
health_wellness
fitness_equipment
jewelry
watches
music_instruments
gaming
computers
mobile_phones
cameras_photo
art_craft
party_supplies
australian_made
```

**Notes on categories:**
- `australian_made` is intentionally distinctive — recruiter signal for AU context awareness
- `outdoor_furniture` + `garden_outdoor` reflect Aussie lifestyle (large outdoor spaces)
- No `winter_sports` (Australia has limited ski culture)
- Underweighted: `wine_alcohol` (regulated category, omitted for simplicity)
- Top 5 categories by product count (40% of products): electronics, fashion_womens, homewares, skincare, sportswear

## Currency and pricing

**Currency:** AUD (Australian Dollar)

**Pricing reference:**
- Median item price: $45
- P95 item price: $250
- P99 item price: $500
- Max item price: $2,000 (electronics outliers)
- Distribution: log-normal with `mean=ln(45)`, `sigma=0.8`

**Freight:**
- Free shipping threshold: $50 (industry standard AU)
- Standard freight: $5-15 metro, $15-30 regional
- Express freight: 2x standard

## Postcode format

Australian postcodes are 4 digits. Range overview:

| State/Territory | Postcode range |
|-----------------|----------------|
| NSW | 1000-2999 |
| ACT | 0200-0299, 2600-2620 |
| VIC | 3000-3999 |
| QLD | 4000-4999 |
| SA | 5000-5999 |
| WA | 6000-6999 |
| TAS | 7000-7999 |
| NT | 0800-0899 |

**Source for geolocation data:** Australia Post Geo data or Open Postcode dataset (loaded once during W2.2 master generator).

## Date conventions

**Timezone:** Australia/Sydney (AEDT/AEST). All Bronze timestamps in this timezone for simplicity. DST transitions ignored (synthetic data tolerance).

**Date format in messages/displays:** DD/MM/YYYY (Australian convention, not US MM/DD/YYYY).

**Business hours:**
- Most orders 10:00-22:00 AEST (matches Olist EDA finding)
- Quiet hours 02:00-08:00

## Holidays affecting volume

Major Australian shopping spikes:

| Event | Date | Volume multiplier |
|-------|------|-------------------|
| Black Friday | Last Friday of November | 4x |
| Cyber Monday | Monday after Black Friday | 3x |
| Boxing Day | December 26 | 3x |
| Boxing Day Sales Week | Dec 26-31 | 1.5x average |
| End of Financial Year sales | June 30 | 2x |
| Mother's Day | 2nd Sunday May | 1.5x |
| Father's Day | 1st Sunday Sept | 1.3x |
| Australia Day | January 26 | 1.3x |

**Public holidays with reduced volume** (drop to 0.7x):
- New Year's Day (Jan 1)
- Anzac Day (Apr 25)
- Christmas Day (Dec 25)

## Day-of-week pattern (matching Olist EDA)

| Day | Weight |
|-----|--------|
| Monday | 1.15 |
| Tuesday | 1.15 |
| Wednesday | 1.05 |
| Thursday | 1.00 |
| Friday | 0.95 |
| Saturday | 0.80 |
| Sunday | 0.85 |

Aussie e-commerce: workweek shopping dominates. Sunday rebounds slightly vs Saturday (weekend planning).

## Hour-of-day pattern (matching Olist EDA)

- 00-09: weight 0.1 (quiet)
- 10-21: weight 1.0 (flat business hours)
- 22-23: weight 0.6 (winding down)

No bimodal noon/evening split — confirmed by Olist EDA.

## Review score conditional distribution

Based on Olist Q22 finding (correlation -0.27 linear, strong non-linear bucket effect):

| Delivery delay vs estimate | Mean review score | Notes |
|---------------------------|-------------------|-------|
| > 7 days ahead | 4.31 | Very early — highest satisfaction |
| 0-7 days ahead | 4.16 | Early |
| 0 to +7 days late | 2.71 | On-time/slightly late — significant drop |
| +7 to +30 days late | 1.65 | Late — strong dissatisfaction |
| > 30 days late | 2.05 | Very late — slight recovery (resignation?) |

Generator should use bucket-conditional sampling (not linear regression).

## Repeat customer behavior

Based on Olist Q18 + Q20 findings:

- ~95% customers are one-and-done
- ~5% are repeaters (2+ orders)
- Repeat distribution heavy-tailed: most repeaters have 2-3 orders, very few have 10+

Generator should pre-allocate ~6,000 unique customers as "repeaters" and reuse their `customer_unique_id` across multiple orders during backfill.