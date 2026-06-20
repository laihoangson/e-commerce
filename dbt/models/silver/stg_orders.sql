-- models/silver/stg_orders.sql
-- Cleaned orders table with parsed timestamps and delivery KPIs.

WITH raw AS (
    SELECT * FROM {{ source('bronze', 'bronze_orders') }}
    WHERE _is_valid = TRUE
),

cleaned AS (
    SELECT
        order_id,
        customer_id,
        order_status,

        -- Parse timestamps (Olist uses string ISO format)
        CAST(order_purchase_timestamp     AS TIMESTAMP) AS purchased_at,
        CAST(order_approved_at            AS TIMESTAMP) AS approved_at,
        CAST(order_delivered_carrier_date AS TIMESTAMP) AS shipped_at,
        CAST(order_delivered_customer_date AS TIMESTAMP) AS delivered_at,
        CAST(order_estimated_delivery_date AS TIMESTAMP) AS estimated_delivery_at,

        -- Delivery KPIs
        CASE
            WHEN order_delivered_customer_date IS NOT NULL
             AND order_estimated_delivery_date IS NOT NULL
             AND CAST(order_delivered_customer_date AS TIMESTAMP)
                 <= CAST(order_estimated_delivery_date AS TIMESTAMP)
            THEN TRUE
            ELSE FALSE
        END AS is_on_time,

        CASE
            WHEN order_delivered_customer_date IS NOT NULL
             AND order_estimated_delivery_date IS NOT NULL
            THEN DATE_DIFF(
                'day',
                CAST(order_estimated_delivery_date AS TIMESTAMP),
                CAST(order_delivered_customer_date AS TIMESTAMP)
            )
            ELSE NULL
        END AS days_late,  -- negative = early, positive = late

        -- Metadata
        _ingested_at,
        _batch_id

    FROM raw
    WHERE order_status NOT IN ('unavailable', 'canceled')
      AND order_purchase_timestamp IS NOT NULL
)

SELECT * FROM cleaned
