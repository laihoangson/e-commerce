-- models/gold/mart_logistics_sla.sql
-- Supply chain command table. One row per order.
-- Powers: OTIF gauge, late delivery heatmap, route analysis, freight analysis.

WITH orders AS (
    SELECT * FROM {{ ref('stg_orders') }}
),

items AS (
    SELECT
        order_id,
        SUM(price)          AS gmv,
        SUM(freight_value)  AS freight_value,
        COUNT(*)            AS item_count,
        seller_state,
        -- For multi-seller orders, take the modal seller state
        MODE(seller_state)  AS primary_seller_state
    FROM {{ ref('stg_order_items') }}
    GROUP BY order_id, seller_state
),

customers AS (
    SELECT customer_id, customer_state, customer_city
    FROM {{ source('bronze', 'bronze_customers') }}
),

geo_seller AS (
    SELECT geolocation_zip_code_prefix, geolocation_lat AS seller_lat, geolocation_lng AS seller_lng
    FROM {{ source('bronze', 'bronze_geolocation') }}
),

geo_customer AS (
    SELECT geolocation_zip_code_prefix, geolocation_lat AS cust_lat, geolocation_lng AS cust_lng
    FROM {{ source('bronze', 'bronze_geolocation') }}
),

sellers AS (
    SELECT seller_id, seller_zip_code_prefix, seller_state
    FROM {{ source('bronze', 'bronze_sellers') }}
),

cust_raw AS (
    SELECT customer_id, customer_zip_code_prefix, customer_state
    FROM {{ source('bronze', 'bronze_customers') }}
)

SELECT
    o.order_id,
    o.customer_id,
    o.order_status,
    o.purchased_at,
    o.approved_at,
    o.shipped_at,
    o.delivered_at,
    o.estimated_delivery_at,
    o.is_on_time,
    o.days_late,

    -- Delivery window in days
    DATE_DIFF('day', o.purchased_at, o.estimated_delivery_at) AS promised_days,
    DATE_DIFF('day', o.purchased_at, o.delivered_at)          AS actual_days,

    -- Seller → Customer route
    i.primary_seller_state                                     AS seller_state,
    c.customer_state,
    i.primary_seller_state || '→' || c.customer_state         AS route_id,

    -- Financials
    i.gmv,
    i.freight_value,
    i.item_count,
    ROUND(i.freight_value / NULLIF(i.gmv, 0) * 100, 2)       AS freight_pct,

    -- Purchase date parts (for time-series filtering)
    DATE_TRUNC('month', o.purchased_at)                        AS order_month,
    EXTRACT(YEAR  FROM o.purchased_at)                         AS order_year,
    EXTRACT(MONTH FROM o.purchased_at)                         AS order_month_num,
    EXTRACT(DOW   FROM o.purchased_at)                         AS order_dow,     -- 0=Sun
    EXTRACT(HOUR  FROM o.purchased_at)                         AS order_hour,

    o._batch_id

FROM orders o
LEFT JOIN (
    SELECT order_id, SUM(price) AS gmv, SUM(freight_value) AS freight_value,
           COUNT(*) AS item_count, MODE(seller_state) AS primary_seller_state
    FROM {{ ref('stg_order_items') }}
    GROUP BY order_id
) i ON o.order_id = i.order_id
LEFT JOIN customers c ON o.customer_id = c.customer_id
WHERE o.delivered_at IS NOT NULL   -- only completed deliveries for SLA analysis
