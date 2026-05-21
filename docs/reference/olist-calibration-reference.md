# Olist EDA — calibration reference for Faker AU realism

## Purpose

This document captures 23 statistical findings from exploratory data analysis of the public Olist Brazilian e-commerce dataset (99,441 orders, 2016-2018). The Olist data itself is **not** in this project's Bronze layer — only its statistical patterns are used to calibrate Faker generators producing 100% Australian-context data.

Numbers in this document directly inform parameters in:
- `pipeline/utils/realism_patterns.py` — distribution constants
- `pipeline/utils/order_generator.py` — time-series + FK chain logic
- `docs/faker-schema-spec.md` — row counts, value ranges

## Source

- **Dataset**: Olist Brazilian e-commerce (Kaggle, CC BY-NC-SA 4.0)
- **URL**: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
- **EDA conducted**: May 2026 by Hoang Son Lai
- **Tools**: DuckDB (read-only VIEWs over Parquet), Python, matplotlib

The original EDA notebook (`01_olist_eda.ipynb`) was deleted after extracting findings to this document. Olist Parquet files are no longer required for this project.

## Part 1 — Schema design findings (Q1-Q10)

### Q1 — Customer master: customer_id vs customer_unique_id

Olist has two customer identifiers: `customer_id` is per-order, `customer_unique_id` is the actual person.

| Metric | Value |
|--------|-------|
| Total customer rows | 99,441 |
| Distinct customer_id | 99,441 |
| Distinct customer_unique_id | 96,096 |

Distribution of orders per unique customer:

| Orders | Customers |
|--------|-----------|
| 1 | 93,099 |
| 2 | 2,745 |
| 3 | 203 |
| 4 | 30 |
| 5 | 8 |
| 6 | 6 |
| 7 | 3 |
| 9 | 1 |
| 17 | 1 |

**Calibration target for Faker:**
- ~95% one-and-done customers
- ~5% repeaters (mostly 2 orders, very few >3)
- Pre-allocate ~6,000 unique customers as repeaters in backfill

## Q2 — Order status distribution

| Status | Orders | % |
|--------|--------|---|
| delivered | 96,478 | 97.02 |
| shipped | 1,107 | 1.11 |
| canceled | 625 | 0.63 |
| unavailable | 609 | 0.61 |
| invoiced | 314 | 0.32 |
| processing | 301 | 0.30 |
| created | 5 | 0.01 |
| approved | 2 | 0.00 |

**Calibration target for Faker:**
- 97% delivered, 1% shipped, 0.5% canceled, rest spread across other statuses
- Only delivered counts toward revenue (`is_revenue` flag in Silver)

## Q3 — Order items per order

88% of orders have a single item; max observed = 21 items.

| n_items | n_orders | % |
|---------|----------|---|
| 1 | 88,863 | 90.06 |
| 2 | 7,516 | 7.62 |
| 3 | 1,322 | 1.34 |
| 4 | 505 | 0.51 |
| 5 | 204 | 0.21 |
| 6 | 198 | 0.20 |
| 7 | 22 | 0.02 |
| 8 | 8 | 0.01 |
| 9 | 3 | 0.00 |
| 10 | 8 | 0.01 |

Aggregate item stats:

| Metric | Value |
|--------|-------|
| Total items | 112,650 |
| Orders with items | 98,666 |
| Avg price | R$120.65 |
| Avg freight | R$19.99 |
| Max price | R$6,735 |
| Zero-price items | 0 |

**Calibration target for Faker:**
- 88% single-item, 12% multi-item (geometric decay)
- Build both `fact_orders` (order-level) + `fact_order_items` (item-level)

## Q4 — Payments per order

5 payment types observed (including 3 anomalous `not_defined` rows):

| Payment type | Count | Avg value | Total value |
|--------------|-------|-----------|-------------|
| credit_card | 76,795 | R$163.32 | R$12,542,084 |
| boleto | 19,784 | R$145.03 | R$2,869,361 |
| voucher | 5,775 | R$65.70 | R$379,437 |
| debit_card | 1,529 | R$142.57 | R$217,990 |
| not_defined | 3 | R$0 | R$0 |

Payment rows per order:

| n_payments | n_orders |
|------------|----------|
| 1 | 96,479 |
| 2 | 2,382 |
| 3 | 301 |
| 4 | 108 |
| 5 | 52 |
| 6+ | ~100 |

Items total vs payment total reconciliation:

| Outcome | Count |
|---------|-------|
| Exact match | 98,296 |
| Minor diff (<R$1) | 120 |
| Major diff (>R$1) | 249 |

**Calibration target for Faker (mapped to AU payment types):**
- 99% single-payment, rest split
- AU type weights: credit_card 45%, debit_card 25%, afterpay 15%, bpay 10%, paypal 5%
- payment_value sum ≈ items_total + freight + small fee/tax adjustment

## Q5 — Review score distribution

| Score | Count | % |
|-------|-------|---|
| 1 | 11,424 | 11.51 |
| 2 | 3,151 | 3.18 |
| 3 | 8,179 | 8.24 |
| 4 | 19,142 | 19.29 |
| 5 | 57,328 | 57.78 |

Review coverage: 99.23% of orders have a review.

**Calibration target for Faker:**
- Heavy 5-star skew (~58%)
- 99% review coverage on delivered orders
- Use conditional sampling on delivery delay (see Q22)

## Q6 — Product categories + seller distribution

Top 10 categories by product count:

| Category | n_products |
|----------|-----------|
| bed_bath_table | 3,029 |
| sports_leisure | 2,867 |
| furniture_decor | 2,657 |
| health_beauty | 2,444 |
| housewares | 2,335 |
| auto | 1,900 |
| computers_accessories | 1,639 |
| toys | 1,411 |
| watches_gifts | 1,329 |
| telephony | 1,134 |

Seller distribution (long-tail):

| Tier | Sellers |
|------|---------|
| Total | 3,095 |
| Power sellers (≥100 orders) | 210 |
| Active (10-99 orders) | 1,061 |
| Small (<10 orders) | 1,824 |

**Calibration target for Faker (AU categories):**
- 5,000 products distributed across 30 AU categories (long-tail)
- Top 5 categories hold ~40% of products
- 500 sellers with similar long-tail: ~30 power sellers, ~170 active, ~300 small

## Q7 — Date range

| Metric | Value |
|--------|-------|
| Earliest order | 2016-09-04 21:15:19 |
| Latest order | 2018-10-17 17:30:18 |
| Span | ~25 months |

Monthly orders showed massive ramp-up: ~10 orders/month in late 2016 → ~8,000/month by mid 2018. September 2018 partial (dataset cutoff mid-month).

**Calibration target for Faker:**
- Faker AU backfill 2023-2026 (~37 months)
- Constant 100 orders/day baseline (no ramp-up; assume mature business)
- Date range allows holiday spike calibration (Black Friday, Boxing Day)

## Q8 — Geography

| Metric | Value |
|--------|-------|
| Total geolocation rows | 1,000,163 |
| Distinct zip prefixes | 19,015 |
| Distinct cities | 8,011 |
| Distinct states | 27 |

Top 10 states by zip count: SP (6,349), MG (1,868), RJ (1,390), RS (1,132), PR (1,046), BA (992), GO (773), SC (620), PE (596), CE (548).

**Calibration target for Faker (AU geography):**
- Use real Australian Post postcode dataset (~2,500 unique postcodes)
- Single row per postcode (not multi-point like Olist)
- 8 states + territories: NSW/VIC/QLD/WA/SA/TAS/ACT/NT

## Q9 — NULL patterns

Orders table NULL counts (out of 99,441):

| Column | NULLs |
|--------|-------|
| order_approved_at | 160 |
| order_delivered_carrier_date | 1,783 |
| order_delivered_customer_date | 2,965 |
| order_estimated_delivery_date | 0 |

Reviews table NULL counts (out of 99,224):

| Column | NULLs |
|--------|-------|
| review_comment_message | 58,247 |
| review_comment_title | 87,656 |
| review_score | 0 |

**Calibration target for Faker:**
- ~3% orders have no `approved_at` (canceled before approval)
- ~3% have no `delivered_customer_date` (in-flight or canceled)
- ~60% of reviews have no comment message
- ~88% have no comment title

## Q10 — Join integrity

| Check | Result |
|-------|--------|
| order_items → orders orphans | 0 |
| order_items → products orphans | 0 |
| order_items → sellers orphans | 0 |
| orders → customers orphans | 0 |

All FK relationships intact. **Calibration target for Faker:** ensure 100% FK integrity in generator chain.

## Part 2A — Data quality findings (Q11-Q14)

These translate to GE rules for W6.

### Q11 — Price distribution

| Metric | Value |
|--------|-------|
| Total items | 112,650 |
| Min price | R$0.85 |
| Max price | R$6,735 |
| Mean | R$120.65 |
| Median (P50) | R$74.99 |
| P95 | R$349.90 |
| P99 | R$890.00 |
| Zero-price items | 0 |
| Above R$1,000 | 844 |
| Above R$5,000 | 3 |

Distribution is log-normal with long tail (verified via log10 histogram showing roughly bell-shaped curve centered around R$100).

**Calibration target for Faker AU:**
- Log-normal: `mean=ln(45)`, `sigma=0.8` → median ~A$45, P99 ~A$300
- Allow rare luxury outliers (>A$500) at low probability
- Zero or negative prices = 0

## Q12 — Timestamp causality violations

Real dirty data found in Olist:

| Violation | Count |
|-----------|-------|
| approved < purchase | 0 |
| shipped < approved | **1,350** |
| delivered < shipped | **23** |
| delivered > estimated (late) | 7,826 |
| estimated < purchase | 0 |

The 1,373 violations are **legitimate data quality issues** — likely seller entry timing errors or timezone mismatches. These should be caught by GE.

**Calibration target for Faker:**
- Inject ~1-2% rows with shipped_before_approved or delivered_before_shipped
- 7,826 / 96,478 delivered = ~8.1% late delivery rate (this is a real KPI, not error)
- GE rules: causality checks must catch injected dirty rows

## Q13 — Negative/zero values

| Check | Count |
|-------|-------|
| Price ≤ 0 in order_items | 0 |
| Freight < 0 in order_items | 0 |
| Payment value < 0 | 0 |
| Payment installments ≤ 0 | **2** |
| Min payment installments | 0 |
| Max payment installments | 24 |
| Review score outside 1-5 | 0 |

**Calibration target for Faker:**
- Inject ~2 rows with `payment_installments=0` for GE demo
- All other value ranges clean
- GE rules: `price > 0`, `freight_value >= 0`, `payment_value > 0`, `payment_installments BETWEEN 1 AND 24`, `review_score BETWEEN 1 AND 5`

## Q14 — Duplicate detection

| Check | Result |
|-------|--------|
| order_id PK uniqueness | 99,441 = 99,441 distinct |
| (order_id, order_item_id) uniqueness | 0 duplicates |

Multiple reviews per order:

| n_reviews | n_orders |
|-----------|----------|
| 1 | 98,126 |
| 2 | 543 |
| 3 | 4 |

~0.5% of orders have re-reviews (not exact duplicates, legitimate re-rating).

**Calibration target for Faker:**
- Inject ~0.5% orders with 2-3 reviews for Silver dedup demo
- GE rule: `order_id` unique in `raw_orders`
- Silver layer: when multiple reviews, keep latest by `review_creation_date`

## Part 2B — Business distribution findings (Q15-Q19)

These shape Gold marts in W8-W9.

### Q15 — Revenue concentration (Pareto)

| Tier | Revenue share |
|------|---------------|
| Top 1% customers | 10.35% |
| Top 10% customers | 38.25% |
| Top 20% customers | 53.53% |
| Total customers | 93,358 |
| Total revenue | R$15,419,774 |

**Key insight**: Olist is **flatter than typical retail** — top 10% holds only 38% revenue (not 80/20). Reason: 95% one-and-done customers buying at similar AOV (R$120 avg). No B2B whales.

**Calibration target for Faker:**
- Mirror flat distribution: top 10% ≈ 38% revenue
- RFM Frequency dimension will be weak (95% have F=1)
- "Champions" segment should be top 5% by Monetary, not top 10%

## Q16 — Geographic concentration

| State | Orders | % |
|-------|--------|---|
| SP | 41,746 | 41.98 |
| RJ | 12,852 | 12.92 |
| MG | 11,635 | 11.70 |
| RS | 5,466 | 5.50 |
| PR | 5,045 | 5.07 |
| SC | 3,637 | 3.66 |
| BA | 3,380 | 3.40 |
| DF | 2,140 | 2.15 |
| ES | 2,033 | 2.04 |
| GO | 2,020 | 2.03 |

Top 3 states = 66.6% of orders.

**Calibration target for Faker AU:**
- Mirror dominance pattern: NSW 32%, VIC 26%, QLD 20% (top 3 = 78%)
- Slightly more concentrated than Olist because AU population is more urban
- Dashboard widget: top-10 states bar chart (not a Brazil/Australia map)

## Q17 — Delivery performance

| Metric | Value |
|--------|-------|
| Avg days to deliver | 12.5 |
| P50 days | 10 |
| P95 days | 29 |
| Late (>estimated) | 7,826 |
| On-time | 88,644 |
| Late % | 8.11 |

Delivery delay distribution is left-skewed (most early, long right tail for late).

**Calibration target for Faker:**
- Mean delivery time: 7 days (faster than Olist due to AU smaller geography)
- 8% late rate
- Estimated delivery date: purchase + 10-14 days (gives buffer)
- Log-normal distribution for actual delivery time

## Q18 — Cohort retention

| Cohort quarter | Cohort size | One-and-done | Repeaters | Repeat rate |
|----------------|-------------|--------------|-----------|-------------|
| 2017-Q1 | 5,152 | 4,891 | 261 | 5.07% |
| 2017-Q2 | 9,087 | 8,608 | 479 | 5.27% |
| 2017-Q3 | 12,208 | 11,635 | 573 | 4.69% |
| 2017-Q4 | 17,261 | 16,702 | 559 | 3.24% |
| 2018-Q1 | 20,441 | 19,805 | 636 | 3.11% |

**Most consequential finding for ML scope.** With ~95% one-and-done, traditional "will churn?" prediction is trivial (almost everyone churns). Reframe required: predict "will reactivate?"

**Calibration target for Faker:**
- Mirror 3-5% repeat rate across cohorts
- Repeaters concentrated in first 6 months after first order
- Cohort matrix `gold.cohort_retention` will show drop from 100% (signup month) to ~3% by month 6

## Q19 — Seasonality + day-of-week

Day-of-week pattern:

| Day | Orders |
|-----|--------|
| Sunday | 11,960 |
| Monday | 16,196 |
| Tuesday | 15,963 |
| Wednesday | 15,552 |
| Thursday | 14,761 |
| Friday | 14,122 |
| Saturday | 10,887 |

Mon-Tue dominant (workweek shopping), weekends dip ~30%.

Hour-of-day pattern: **flat 10-22h** (not bimodal as initially expected). Quiet 2-5am. Brazilian e-commerce = all-day shopping.

Black Friday 2017 (Nov 24): clearly visible spike, ~3x normal day volume.

**Calibration target for Faker:**
- DOW weights: Mon 1.15, Tue 1.15, Wed 1.05, Thu 1.0, Fri 0.95, Sat 0.80, Sun 0.85
- Hour: flat 10-22h weight 1.0, drop to 0.1 between 2-9am, 0.6 between 22-23h
- Holiday spikes: Black Friday 4x, Boxing Day 3x, EOFY 2x, Mother's Day 1.5x, Father's Day 1.3x, Australia Day 1.3x
- Reduced volume: Christmas Day, New Year, Anzac Day → 0.7x

## Part 2C — ML signal findings (Q20-Q23)

These adjust ML scope in W11-W15.

### Q20 — Churn signal (one-and-done vs repeaters)

| Segment | Count | Avg item value | Avg review score | Avg delivery days |
|---------|-------|----------------|------------------|-------------------|
| one_and_done | 90,557 | R$146.68 | 4.15 | 12.5 |
| repeater | 2,801 | R$124.62 | 4.20 | 12.2 |

Differences exist but small. Repeaters: slightly higher reviews, slightly lower AOV, marginally faster delivery.

**Implication for ML**: baseline features have weak signal alone. Need temporal features (last_order_days_ago, seasonality position, RFM segment) for model to work.

## Q21 — Fraud signal: velocity + high-value first orders

First-order value buckets:

| Bucket | n_first_orders |
|--------|----------------|
| R$100-500 | 45,979 |
| <R$100 | 45,280 |
| R$500-1,000 | 3,007 |
| >R$1,000 | 1,830 |

Velocity:

| Window | Count |
|--------|-------|
| Same customer ordering within 1h | 920 |
| Within 1 day | 112 |

**Implication for ML**: Olist has NO IP/device data → traditional fraud features missing. High-value first orders + velocity rare. Pivot W11+ from "fraud detection" to **product recommendation** (more signal in order_items co-occurrence).

## Q22 — Review predictability from delivery

| Delivery delay vs estimate | Mean review score | Count |
|---------------------------|-------------------|-------|
| Very early (>7d ahead) | 4.31 | 76,170 |
| Early (0-7d ahead) | 4.16 | 13,769 |
| On time (±0 to +7d) | 2.71 | 3,612 |
| Late (+7 to +30d) | 1.65 | 2,466 |
| Very late (>30d) | 2.05 | 331 |

Pearson correlation: **-0.267** (linear). But non-linear effect is massive: review drops from 4.31 → 2.71 at the on-time threshold.

**Calibration target for Faker:**
- Conditional sampling on delivery delay bucket, not linear correlation
- ML feature engineering: use `is_late` binary + `delay_bucket` categorical, not raw `delay_days`

## Q23 — Churn class imbalance

Using 90-day inactive definition relative to dataset's max date:

| Outcome | Count | % |
|---------|-------|---|
| Total customers | 93,358 | 100 |
| Churned (>90 days inactive) | 83,999 | 89.98 |
| Active (≤90 days) | 9,359 | 10.02 |

**Implication for ML**: extreme class imbalance. Standard accuracy metric useless. Must use PR-AUC, class weighting, and reframe target.

**Reframed target**: "Will reactivate in next 30 days?" (rarer positive class, ~3-5%) instead of "Will churn?".

## Summary — 23 calibration parameters

For quick reference when coding `realism_patterns.py`:

| # | Parameter | Value |
|---|-----------|-------|
| 1 | Unique customer ratio | 96% |
| 2 | Delivered order ratio | 97% |
| 3 | Single-item order ratio | 88% |
| 4 | Single-payment ratio | 97% |
| 5 | 5-star review ratio | 58% |
| 5b | Review coverage | 99% |
| 6 | Power seller ratio | 7% of sellers |
| 7 | Daily order volume | 100/day (constant, not ramp) |
| 8 | Distinct postcodes | ~2,500 |
| 9 | Null approved_at ratio | 0.16% |
| 9b | Null delivered_date ratio | 3% |
| 10 | FK orphan ratio | 0% |
| 11 | Price log-normal sigma | 0.8 (median ~$45) |
| 12 | Causality violation ratio | 1.4% |
| 12b | Late delivery ratio | 8.1% |
| 13 | Bad installments ratio | 0.002% |
| 14 | Duplicate review ratio | 0.5% |
| 15 | Top 10% revenue share | 38% |
| 16 | Top 3 states share | 67% (AU: 78%) |
| 17 | Mean delivery days | 12.5 (AU: 7) |
| 18 | Repeat customer ratio | 5% |
| 19 | DOW Mon-Tue weight | 1.15 |
| 19b | Hour 10-22 weight | 1.0 |
| 19c | Black Friday multiplier | 3-4x |
| 22 | Review-delivery bucket means | 4.31/4.16/2.71/1.65/2.05 |
| 23 | 90-day churn ratio | 90% |

## Notes for Faker AU adaptations

Brazilian → Australian context mapping is NOT direct copy. Some patterns will differ:

| Pattern | Olist BR | Faker AU |
|---------|----------|----------|
| Mean delivery days | 12.5 | 7 (smaller geography) |
| Top 3 states share | 67% | 78% (more urban concentration) |
| Payment installments | 1-24 typical | 1-12 typical (AU credit market different) |
| Boleto/cash-equivalent share | 19% | BPAY 10% (less prevalent) |
| Afterpay (BNPL) | N/A | 15% (Aussie fintech pride) |

These adaptations documented in `docs/au-entities.md`.