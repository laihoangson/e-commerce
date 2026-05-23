"""Per-row validity rules for Bronze tables.

Each rule is a SQL boolean expression that evaluates to TRUE for a VALID row.
validate_bronze.py uses these to set the _is_valid column row-by-row, catching
exactly the defects the order generator injects (negative prices, impossible
lifecycle timestamps, bad installments) plus basic null/range checks.

Tables not listed here have all rows marked valid (masters are clean).
"""

from __future__ import annotations

# table -> SQL expression that is TRUE when the row is valid.
VALIDITY_RULES: dict[str, str] = {
    "raw_orders": """
        order_id IS NOT NULL
        AND customer_id IS NOT NULL
        AND order_purchase_timestamp IS NOT NULL
        AND order_status IN
            ('delivered','shipped','canceled','unavailable','invoiced',
             'processing','created','approved')
        -- lifecycle timestamps must be ordered when present
        AND (order_approved_at IS NULL
             OR order_approved_at >= order_purchase_timestamp)
        AND (order_delivered_customer_date IS NULL
             OR order_delivered_customer_date >= order_purchase_timestamp)
    """,
    "raw_order_items": """
        order_id IS NOT NULL
        AND product_id IS NOT NULL
        AND price > 0
        AND freight_value >= 0
    """,
    "raw_payments": """
        order_id IS NOT NULL
        AND payment_type IN
            ('credit_card','boleto','voucher','debit_card','not_defined')
        AND payment_installments BETWEEN 0 AND 24
        AND payment_value >= 0
    """,
    "raw_reviews": """
        review_id IS NOT NULL
        AND order_id IS NOT NULL
        AND review_score BETWEEN 1 AND 5
    """,
    "raw_customers": "customer_id IS NOT NULL AND customer_unique_id IS NOT NULL",
    "raw_products": "product_id IS NOT NULL AND product_category_name IS NOT NULL",
    "raw_sellers": "seller_id IS NOT NULL",
    "raw_geolocation": "geolocation_postcode IS NOT NULL",
    "raw_category_translation": "product_category_name IS NOT NULL",
}
