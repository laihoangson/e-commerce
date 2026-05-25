## Bronze Schema Specification

The 9 Bronze tables, loaded from Olist and appended by the live tail. All are
DuckDB native TABLEs in the `bronze` schema. Every row carries metadata columns:

| Column | Type | Meaning |
| - | - | - |
| _ingested_at | TIMESTAMP | when the row was written to Bronze |
| _source_file | VARCHAR | logical loader (load_olist_bronze / live_generator) |
| _batch_id | VARCHAR | run identifier |
| _is_valid | BOOLEAN | set by Great Expectations; NULL at load time |
| _data_source | VARCHAR | 'olist' (real) or 'faker_live' (synthetic) |

### Master tables

raw_geolocation - postcode prefix, lat, lng, city, state (deduplicated to one
row per postcode prefix).

raw_category_translation - Portuguese category name and English translation.

raw_sellers - seller_id, postcode, city, state.

raw_products - product_id, category, weight and dimensions. Note: base_price is
not present in Olist; item prices live in raw_order_items.

### Customers

raw_customers - one row per order, with a per-order customer_id and a stable
customer_unique_id (the repeat key), plus postcode, city, state.

### Transactional

raw_orders - order_id, customer_id, order_status, five lifecycle timestamps
(purchase, approved, carrier handoff, customer delivery, estimate), and
ab_experiment / ab_variant (NULL for Olist, populated for the live tail).

raw_order_items - order_id, order_item_id, product_id, seller_id, price,
freight_value.

raw_payments - order_id, payment_sequential, payment_type, payment_installments,
payment_value. Brazilian payment types: credit_card, boleto, voucher,
debit_card.

raw_reviews - review_id, order_id, review_score (1-5), comment title and
message (real free text in the Olist core), review_creation_date.

### Validation

Great Expectations validates each table and sets `_is_valid` per row. Expected
findings on the real Olist data include around 610 products with a missing
category - a genuine data-quality issue the suite is designed to catch.
