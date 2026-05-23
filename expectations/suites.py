"""Great Expectations suite definitions for Bronze tables.

Each suite is a list of expectation specs (GE 1.x gx.expectations classes).
Suites are used by validate_bronze.py to produce a validation report.

Row-level _is_valid flagging is handled separately by the SQL rules in
row_validity_rules.py, because GE expectations operate at the column/aggregate
level while _is_valid is a per-row verdict.
"""

from __future__ import annotations

import great_expectations as gx

# Map: table name -> list of GE expectation objects.
SUITES: dict[str, list] = {
    "raw_orders": [
        gx.expectations.ExpectColumnValuesToNotBeNull(column="order_id"),
        gx.expectations.ExpectColumnValuesToBeUnique(column="order_id"),
        gx.expectations.ExpectColumnValuesToNotBeNull(column="customer_id"),
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="order_status",
            value_set=[
                "delivered",
                "shipped",
                "canceled",
                "unavailable",
                "processing",
            ],
        ),
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="order_purchase_timestamp"
        ),
    ],
    "raw_order_items": [
        gx.expectations.ExpectColumnValuesToNotBeNull(column="order_id"),
        gx.expectations.ExpectColumnValuesToNotBeNull(column="product_id"),
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="price", min_value=0, strict_min=True
        ),
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="freight_value", min_value=0
        ),
    ],
    "raw_payments": [
        gx.expectations.ExpectColumnValuesToNotBeNull(column="order_id"),
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="payment_type",
            value_set=["credit_card", "debit_card", "afterpay", "bpay", "paypal"],
        ),
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="payment_installments", min_value=1, max_value=24
        ),
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="payment_value", min_value=0, strict_min=True
        ),
    ],
    "raw_reviews": [
        gx.expectations.ExpectColumnValuesToNotBeNull(column="review_id"),
        gx.expectations.ExpectColumnValuesToNotBeNull(column="order_id"),
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="review_score", min_value=1, max_value=5
        ),
    ],
    "raw_customers": [
        gx.expectations.ExpectColumnValuesToNotBeNull(column="customer_id"),
        gx.expectations.ExpectColumnValuesToBeUnique(column="customer_id"),
        gx.expectations.ExpectColumnValuesToNotBeNull(column="customer_unique_id"),
    ],
    "raw_products": [
        gx.expectations.ExpectColumnValuesToNotBeNull(column="product_id"),
        gx.expectations.ExpectColumnValuesToBeUnique(column="product_id"),
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="product_category_name"
        ),
    ],
    "raw_sellers": [
        gx.expectations.ExpectColumnValuesToNotBeNull(column="seller_id"),
        gx.expectations.ExpectColumnValuesToBeUnique(column="seller_id"),
    ],
}
