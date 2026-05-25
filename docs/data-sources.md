## Data Sources

RetailLens uses a hybrid dataset: a real historical core plus a small synthetic
live tail. This document describes both and the boundary between them.

### Historical core - Olist (real)

The Olist Brazilian e-commerce dataset: around 99,000 real orders placed on the
Olist marketplace between September 2016 and October 2018. Loaded into Bronze
from 9 CSV files via `pipeline/load_olist_bronze.py`. All rows are tagged
`_data_source = 'olist'`.

Key real-world characteristics (reflected throughout the dashboard and models):

- Currency: Brazilian Real (BRL)
- Payment types: credit_card, boleto, voucher, debit_card
- Geography: 27 Brazilian states; Sao Paulo (SP) dominates volume
- Repeat-purchase rate around 3 percent (one-and-done marketplace)
- Review scores skew high; late delivery correlates with low scores
- About 610 products have a missing category (a known data-quality issue,
  flagged by Great Expectations)

### Live tail - synthetic (disclosed)

A small Faker-generated stream (2024-2026, around 20 orders/day) continuing the
timeline, produced by `pipeline/live_generator.py`. Tagged
`_data_source = 'faker_live'`. Purposes:

- Keep the dashboard current (a live-feeling "today")
- Host controlled A/B experiments (the real Olist core has none)
- Provide learnable reactivation signal (see below)

The live tail reuses the real Olist product, seller, and customer pools rather
than inventing new master data, so it stays consistent with the core.

### Disclosed synthetic structure

Two patterns are deliberately encoded into the live tail. Both are documented
here so the analysis stays honest:

1. A/B effect: the `welcome_voucher` experiment gives variant B a +15 percent
   order-value uplift; `free_shipping_threshold` is a null control. This lets
   the A/B engine demonstrate both detecting a real effect and correctly
   finding none.

2. Loyalty signal: each live customer has a hidden loyalty propensity (skewed
   low, most customers are one-and-done). Higher-propensity customers are
   sampled more often (producing repeat purchases) and tend to leave higher
   review scores. The relationship is noisy, so the reactivation model learns
   real but imperfect signal rather than a trivial one.

The real Olist core is never modified; these patterns exist only in the
synthetic tail.
