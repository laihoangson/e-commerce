# Faker Bronze Schema Specification

Defines the 9 Bronze tables RetailLens generates. All are DuckDB native TABLEs in
the `bronze` schema. Every table carries 4 metadata columns appended at write time:

| Column | Type | Meaning |
|--------|------|---------|
| _ingested_at | TIMESTAMP | when the row was written to Bronze |
| _source_file | VARCHAR | logical source (e.g. 'order_generator') |
| _batch_id | VARCHAR | run identifier (UUID per pipeline run) |
| _is_valid | BOOLEAN | set by Great Expectations in Phase 3; NULL at generation time |

Tables are grouped by generation tier. A generator in a later tier may reference
keys produced by an earlier tier (the FK chain).

## Tier 0 — master tables

### raw_geolocation (~2,500 rows)

| Column | Type | Notes |
|--------|------|-------|
| geolocation_postcode | VARCHAR | 4-digit AU postcode |
| geolocation_lat | DOUBLE | latitude |
| geolocation_lng | DOUBLE | longitude |
| geolocation_city | VARCHAR | city name |
| geolocation_state | VARCHAR | state code |

### raw_category_translation (30 rows)

Identity mapping kept for schema symmetry with marketplace datasets.

| Column | Type | Notes |
|--------|------|-------|
| product_category_name | VARCHAR | category key |
| product_category_name_english | VARCHAR | same value (identity) |

### raw_sellers (500 rows)

| Column | Type | Notes |
|--------|------|-------|
| seller_id | VARCHAR | UUID |
| seller_postcode | VARCHAR | FK -> raw_geolocation |
| seller_city | VARCHAR | |
| seller_state | VARCHAR | |

### raw_products (5,000 rows)

| Column | Type | Notes |
|--------|------|-------|
| product_id | VARCHAR | UUID |
| product_category_name | VARCHAR | FK -> raw_category_translation |
| product_weight_g | INTEGER | |
| product_length_cm | INTEGER | |
| product_height_cm | INTEGER | |
| product_width_cm | INTEGER | |
| base_price | DOUBLE | reference price, log-normal |

## Tier 1 — customers

### raw_customers (~87k rows, one per order)

| Column | Type | Notes |
|--------|------|-------|
| customer_id | VARCHAR | UUID, unique per order |
| customer_unique_id | VARCHAR | stable across orders; ~5% repeat |
| customer_postcode | VARCHAR | FK -> raw_geolocation |
| customer_city | VARCHAR | |
| customer_state | VARCHAR | |

## Tier 2 — transactional (order generator emits all of these together)

### raw_orders (~87k rows)

| Column | Type | Notes |
|--------|------|-------|
| order_id | VARCHAR | UUID |
| customer_id | VARCHAR | FK -> raw_customers |
| order_status | VARCHAR | delivered/shipped/canceled/... |
| order_purchase_timestamp | TIMESTAMP | |
| order_approved_at | TIMESTAMP | nullable |
| order_delivered_carrier_date | TIMESTAMP | nullable |
| order_delivered_customer_date | TIMESTAMP | nullable |
| order_estimated_delivery_date | TIMESTAMP | |
| ab_experiment | VARCHAR | experiment name or NULL |
| ab_variant | VARCHAR | 'A'/'B' or NULL |

### raw_order_items (~103k rows)

| Column | Type | Notes |
|--------|------|-------|
| order_id | VARCHAR | FK -> raw_orders |
| order_item_id | INTEGER | 1-based sequence within order |
| product_id | VARCHAR | FK -> raw_products |
| seller_id | VARCHAR | FK -> raw_sellers |
| price | DOUBLE | |
| freight_value | DOUBLE | |

### raw_payments (~87k rows)

| Column | Type | Notes |
|--------|------|-------|
| order_id | VARCHAR | FK -> raw_orders |
| payment_sequential | INTEGER | usually 1 |
| payment_type | VARCHAR | credit_card/debit_card/afterpay/bpay/paypal |
| payment_installments | INTEGER | 1–24 for credit_card, else 1 |
| payment_value | DOUBLE | order item total + freight |

### raw_reviews (~84k rows)

| Column | Type | Notes |
|--------|------|-------|
| review_id | VARCHAR | UUID |
| order_id | VARCHAR | FK -> raw_orders |
| review_score | INTEGER | 1–5, conditional on delivery delay |
| review_comment_title | VARCHAR | nullable |
| review_comment_message | VARCHAR | nullable |
| review_creation_date | TIMESTAMP | |

## A/B experiments

Orders carry `ab_experiment` + `ab_variant` so the Phase 5 A/B engine can
analyze them. Pre-defined experiments:

| Experiment | Variant A | Variant B |
|------------|-----------|-----------|
| free_shipping_threshold | A$50 | A$100 |
| welcome_voucher | 10% | 20% |

A subset of orders is assigned to an experiment; the rest have NULL.

## Generation order (FK chain)

```
Tier 0: geolocation + categories  ->  sellers + products
Tier 1: customers
Tier 2: orders -> order_items -> payments -> reviews
```

Master tables are generated once (idempotent). Customers and transactional
tables are generated per backfill run and appended in live mode.
