# Faker AU Bronze schema specification

## Overview

This document specifies the 9 tables in the Bronze layer of RetailLens. All data is synthetically generated using Faker in Australian e-commerce context (2023-2026). Schema concept mirrors the Olist Brazilian e-commerce dataset to facilitate distribution calibration, but values are 100% Australian native.

## Design principles

### Data generation strategy

Tables fall into two categories:

**Master tables** (static, generated once at init):
- `raw_products` — ~5,000 rows
- `raw_sellers` — ~500 rows
- `raw_category_translation` — ~30 rows
- `raw_geolocation` — ~2,500 rows

**Transactional tables** (time-series, backfill 2023-2026 + live during 2026):
- `raw_customers` — ~118,000 unique customers across backfill
- `raw_orders` — ~124,000 orders (100/day × ~1,240 days)
- `raw_order_items` — ~140,000 items (88% single-item, 12% multi-item)
- `raw_payments` — ~129,000 payment rows (99% single-payment)
- `raw_reviews` — ~123,000 reviews (99% coverage)

### Foreign key consistency

Generator chain ensures FK integrity:
1. Master tables built first
2. Customer generated, gets `customer_unique_id`
3. Order generated with new `customer_id` (per-order ID), references `customer_unique_id`
4. Order items generated 1-N per order, reference real `product_id` + `seller_id` from masters
5. Payments generated 1-3 per order, sum approximates `items_total`
6. Reviews generated for 99% of orders with delivery delay correlated to score

### Metadata columns (every Bronze table)

All Bronze tables carry 4 metadata columns appended by ingestion:

| Column | Type | Purpose |
|--------|------|---------|
| `_ingested_at` | TIMESTAMP | When this batch was inserted |
| `_source_file` | VARCHAR | Generator name (e.g. "faker_order_generator") |
| `_batch_id` | VARCHAR | UUID per pipeline run |
| `_is_valid` | BOOLEAN | Default TRUE; overwritten by Great Expectations in W6 |

### Dirty data injection

Generators inject ~1-2% dirty rows to demonstrate Great Expectations later:
- Timestamp causality violations (delivered before shipped)
- payment_installments = 0
- payment_value < 0
- review_score outside 1-5 range
- Duplicate (order_id, order_item_id) combos

These rows have `_is_valid=TRUE` initially; GE will set FALSE in W6.

## Table 1 — bronze.raw_customers

Master of customer records. One row per (customer, order) — same person buying twice has two rows with same `customer_unique_id` but different `customer_id`.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `customer_id` | VARCHAR(32) | Generated UUID | Unique per row |
| `customer_unique_id` | VARCHAR(32) | Generated UUID | Stable per real person; ~95% appear once, ~5% repeat |
| `customer_zip_code_prefix` | VARCHAR(4) | Sampled from `raw_geolocation` | 4-digit Australian postcode |
| `customer_city` | VARCHAR | Sampled from `raw_geolocation` | Australian city name |
| `customer_state` | VARCHAR(3) | Sampled by population weight | NSW/VIC/QLD/WA/SA/TAS/ACT/NT |
| `_ingested_at`, `_source_file`, `_batch_id`, `_is_valid` | metadata | — | — |

**Generation logic:**
- State sampled by population weight (NSW 32%, VIC 26%, QLD 20%, WA 11%, SA 7%, TAS 2%, ACT 1.5%, NT 0.5%)
- City sampled from postcodes within selected state
- `customer_unique_id` reused for repeat customers (5% rate)

## Table 2 — bronze.raw_orders

Master of orders. Each row = 1 order placed by a customer.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `order_id` | VARCHAR(32) | Generated UUID | Unique |
| `customer_id` | VARCHAR(32) | FK to `raw_customers` | Per-order ID |
| `order_status` | VARCHAR | Weighted random | 97% delivered, 1% shipped, 0.5% canceled, rest other |
| `order_purchase_timestamp` | TIMESTAMP | Time-series generator | DOW + hour-of-day patterns |
| `order_approved_at` | TIMESTAMP | purchase + random(0-60min) | NULL if canceled before approval (~0.2%) |
| `order_delivered_carrier_date` | TIMESTAMP | approved + random(1-3 days) | NULL if not yet shipped |
| `order_delivered_customer_date` | TIMESTAMP | shipped + lognormal(mean=7d) | NULL if in-flight |
| `order_estimated_delivery_date` | DATE | purchase + 10-14 days | Always populated |
| `_ingested_at`, `_source_file`, `_batch_id`, `_is_valid` | metadata | — | — |

**Realism patterns:**
- Day-of-week: Mon-Tue weight 1.15, Sun-Sat weight 0.8 (matching Olist EDA)
- Hour-of-day: flat 10-22h, drop sharply 23h-9h
- Black Friday weekend (last Fri-Mon Nov): 4x normal volume
- Boxing Day (Dec 26): 3x normal volume
- 8% of delivered orders have `delivered_customer_date > estimated_delivery_date` (late)
- Backfill 2023-01-01 to today, live mode generates today's orders only

## Table 3 — bronze.raw_order_items

Items within orders. One row per (order, item_sequence).

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `order_id` | VARCHAR(32) | FK to `raw_orders` | — |
| `order_item_id` | INT | Sequence 1, 2, 3... within order | — |
| `product_id` | VARCHAR(32) | FK to `raw_products` | — |
| `seller_id` | VARCHAR(32) | FK to `raw_sellers` | — |
| `shipping_limit_date` | TIMESTAMP | purchase + 2 days | Deadline seller must ship |
| `price` | DECIMAL(10,2) | Log-normal sampling | AUD, median ~$45, max ~$2000 |
| `freight_value` | DECIMAL(10,2) | Distance-based | AUD, 0 to ~$30 |
| `_ingested_at`, `_source_file`, `_batch_id`, `_is_valid` | metadata | — | — |

**Realism patterns:**
- Items per order: 88% have 1 item, 8% have 2 items, 4% have 3+ items (max 10)
- Price distribution: log-normal with `mean=ln(45)`, `sigma=0.8` → median $45, P99 ~$300
- Some products are luxury outliers (>$500) with low probability
- Freight value: 0 (free shipping over $50 threshold) or distance-based 5-30 AUD

## Table 4 — bronze.raw_payments

Payments per order. Multiple rows per order if split payment.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `order_id` | VARCHAR(32) | FK to `raw_orders` | — |
| `payment_sequential` | INT | 1, 2, 3... within order | — |
| `payment_type` | VARCHAR | Weighted random | credit_card/debit_card/afterpay/bpay/paypal |
| `payment_installments` | INT | 1-24 for credit_card; 1 for others | Brazilian-style instalments |
| `payment_value` | DECIMAL(10,2) | Calculated from items total | AUD |
| `_ingested_at`, `_source_file`, `_batch_id`, `_is_valid` | metadata | — | — |

**Realism patterns:**
- Payment types weighted: credit_card 45%, debit_card 25%, afterpay 15%, bpay 10%, paypal 5%
- 99% of orders have 1 payment row; rest split (e.g. afterpay + credit_card)
- payment_value sum per order ≈ items_total + freight_total + small fee (0-3%)
- credit_card installments: weighted toward 1-3 installments, occasional 6/12/24

## Table 5 — bronze.raw_reviews

Reviews after delivery. ~99% of delivered orders get reviewed.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `review_id` | VARCHAR(32) | Generated UUID | Unique |
| `order_id` | VARCHAR(32) | FK to `raw_orders` | — |
| `review_score` | INT | Score-by-delivery correlation | 1-5 stars |
| `review_comment_title` | VARCHAR | Optional template | ~30% populated |
| `review_comment_message` | VARCHAR | Optional template | ~30% populated |
| `review_creation_date` | TIMESTAMP | delivered + 1-7 days | When email sent |
| `review_answer_timestamp` | TIMESTAMP | creation + 0-3 days | When customer responded |
| `_ingested_at`, `_source_file`, `_batch_id`, `_is_valid` | metadata | — | — |

**Realism patterns:**
- 99% review coverage on delivered orders
- Score distribution conditional on delivery performance:
  - very_early (>7d ahead of estimate): 4.31 mean (mostly 5s)
  - early (0-7d ahead): 4.16 mean
  - on_time (±0 to +7d): 2.71 mean
  - late (+7 to +30d): 1.65 mean
  - very_late (>30d): 2.05 mean
- Comment text from rotating templates (positive vs negative phrases) keyed on score
- ~0.5% orders have duplicate reviews (re-review, not exact dup)

## Table 6 — bronze.raw_products

Catalog of products available for sale.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `product_id` | VARCHAR(32) | Generated UUID | Unique |
| `product_category_name` | VARCHAR | Sampled from 30 AU categories | Snake_case English |
| `product_name_length` | INT | Random 10-80 | Char count of product name |
| `product_description_length` | INT | Random 50-500 | Char count of description |
| `product_photos_qty` | INT | Random 1-8 | Number of photos |
| `product_weight_g` | INT | Category-dependent | g, 50-50000 |
| `product_length_cm` | INT | Category-dependent | cm, 5-200 |
| `product_height_cm` | INT | Category-dependent | cm, 2-100 |
| `product_width_cm` | INT | Category-dependent | cm, 5-150 |
| `_ingested_at`, `_source_file`, `_batch_id`, `_is_valid` | metadata | — | — |

**Realism patterns:**
- 5,000 products distributed across 30 categories (long-tail: top 5 categories hold 40% of products)
- Weight + dimensions correlated with category (electronics small/light, furniture large/heavy)

## Table 7 — bronze.raw_sellers

Master of sellers.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `seller_id` | VARCHAR(32) | Generated UUID | Unique |
| `seller_zip_code_prefix` | VARCHAR(4) | Sampled from `raw_geolocation` | — |
| `seller_city` | VARCHAR | Matched to zip prefix | — |
| `seller_state` | VARCHAR(3) | Matched to zip prefix | — |
| `_ingested_at`, `_source_file`, `_batch_id`, `_is_valid` | metadata | — | — |

**Realism patterns:**
- 500 sellers total
- Geographic distribution: NSW 35%, VIC 28%, QLD 18%, WA 10%, others 9% (slight skew vs customer states)
- Long-tail order distribution (will emerge from order_items generator): top 50 sellers handle ~40% volume

## Table 8 — bronze.raw_geolocation

Australian postcode reference data.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `geolocation_zip_code_prefix` | VARCHAR(4) | Real AU postcodes | First 4 digits |
| `geolocation_lat` | DECIMAL(10,7) | Real coordinates | Pre-loaded dataset |
| `geolocation_lng` | DECIMAL(10,7) | Real coordinates | — |
| `geolocation_city` | VARCHAR | Real city names | — |
| `geolocation_state` | VARCHAR(3) | NSW/VIC/QLD/... | — |
| `_ingested_at`, `_source_file`, `_batch_id`, `_is_valid` | metadata | — | — |

**Source:** Loaded once from Australia Post or a public dataset (~2,500 unique postcodes covering populated areas). Single row per postcode (unlike Olist which had multiple lat/lng per zip).

## Table 9 — bronze.raw_category_translation

Translation lookup table. In AU context, all categories are already English so this table is technically redundant. Kept for schema symmetry with Olist concept.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `product_category_name` | VARCHAR | Snake_case English | e.g. "outdoor_furniture" |
| `product_category_name_english` | VARCHAR | Same as above | Identity for AU |
| `_ingested_at`, `_source_file`, `_batch_id`, `_is_valid` | metadata | — | — |

## Relationships

```
CUSTOMERS (per-order rows)
  └─ customer_id ──→ ORDERS
                       ├─ order_id ──→ ORDER_ITEMS ──→ PRODUCTS
                       │                              ──→ SELLERS
                       ├─ order_id ──→ PAYMENTS
                       └─ order_id ──→ REVIEWS

CUSTOMERS.zip ──→ GEOLOCATION
SELLERS.zip   ──→ GEOLOCATION
PRODUCTS.category ──→ CATEGORY_TRANSLATION
```

## Storage estimate

Backfill 2023-2026 sizing:

| Table | Rows | Avg row size | Total |
|-------|------|--------------|-------|
| raw_customers | 124k | 150 B | 18 MB |
| raw_orders | 124k | 200 B | 25 MB |
| raw_order_items | 140k | 100 B | 14 MB |
| raw_payments | 129k | 80 B | 10 MB |
| raw_reviews | 123k | 200 B | 25 MB |
| raw_products | 5k | 200 B | 1 MB |
| raw_sellers | 500 | 100 B | 50 KB |
| raw_geolocation | 2.5k | 100 B | 250 KB |
| raw_category_translation | 30 | 100 B | 3 KB |
| **Total uncompressed** | | | **~93 MB** |
| **DuckDB compressed** | | | **~30-40 MB** |

Under Supabase 50 MB upload cap. Confirmed feasible.
