# Olist Calibration Reference

RetailLens generates 100% synthetic Australian data. To make that data realistic
rather than uniform-random, the generators are calibrated against published
distributions of the Olist Brazilian e-commerce dataset (99k real orders,
2016–2018). **No Olist rows enter the pipeline** — only these aggregate patterns
inform the samplers.

Calibration target: Realism Level 2 — match marginal distributions and a few key
conditional ones, not full multivariate fidelity.

## Order volume and seasonality

- Backfill window: 2024-01-01 to 2026-05-30 (~2 years, ~881 days)
- Base rate: ~100 orders/day; after day-of-week multipliers (avg ~0.99)
  this yields ~87k total orders
- Day-of-week seasonality: Monday–Tuesday peak, weekend trough
  (multipliers roughly Mon 1.15, Tue 1.15, Wed 1.05, Thu 1.0, Fri 0.95,
  Sat 0.85, Sun 0.85)

## Order item structure

- ~88% of orders are single-item; remainder up to ~5 items, decaying
- Unit price: log-normal, median ~A$90, long right tail to ~A$2,000
- Freight value: roughly 8–22% of item price, with a small fixed floor

## Reviews

- ~99% of delivered orders carry a review
- Review score distribution skews high: ~58% 5-star, ~19% 4-star,
  ~8% 3-star, ~7% 2-star, ~8% 1-star
- Score is conditional on delivery delay: late deliveries shift mass toward
  1–2 stars

## Delivery lifecycle

- ~97% of orders reach `delivered` status; remainder split across
  shipped/canceled/unavailable/processing
- ~8% of delivered orders are late (actual delivery later than estimated)
- Five lifecycle timestamps per order, strictly ordered when present:
  purchase → approved → carrier handoff → customer delivery → estimate

## Customers

- Repeat-purchase rate is low: ~5% of customers place more than one order
- Modeled with two IDs: a per-order `customer_id` and a stable
  `customer_unique_id` (the repeat key)

## Payments

- ~99% of orders are paid with a single payment record
- credit_card installments span 1–24; most orders are 1–4 installments

## Sellers and products

- Sellers: ~500, long-tail order volume (a few large sellers, many tiny ones)
- Products: ~5,000, long-tail across the 30 categories

## Intentional data quality issues

To exercise Great Expectations in Phase 3, ~1–2% of Bronze rows are deliberately
"dirty":
- Out-of-order or impossible lifecycle timestamps
- Invalid installment counts (e.g. installments on non-credit_card)
- Occasional negative or zero prices

These rows are written to Bronze with `_is_valid` left for GE to set in Phase 3.
