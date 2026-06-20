-- models/gold/mart_sales_and_demand.sql
-- Monthly demand time-series. Powers: Prophet forecasting, revenue trend chart,
-- seasonal decomposition, stockout proxy.
-- Fix: added WHERE i.category_en IS NOT NULL to exclude unmatched LEFT JOIN rows.

WITH orders AS (
    SELECT * FROM {{ ref('stg_orders') }}
),

items AS (
    SELECT * FROM {{ ref('stg_order_items') }}
)

SELECT
    DATE_TRUNC('month', o.purchased_at)             AS ds,
    i.category_en                                    AS product_category,

    COUNT(DISTINCT o.order_id)                       AS order_count,
    COUNT(i.order_item_id)                           AS item_count,

    ROUND(SUM(i.price), 2)                           AS revenue,
    ROUND(SUM(i.freight_value), 2)                   AS freight_revenue,
    ROUND(SUM(i.price + i.freight_value), 2)         AS total_revenue,
    ROUND(AVG(i.price), 2)                           AS avg_item_price,

    COUNT(DISTINCT CASE WHEN o.order_status = 'canceled' THEN o.order_id END)
        AS canceled_orders,
    ROUND(
        COUNT(DISTINCT CASE WHEN o.order_status = 'canceled' THEN o.order_id END) * 1.0
        / NULLIF(COUNT(DISTINCT o.order_id), 0) * 100,
    2) AS cancellation_rate_pct,

    ROUND(AVG(CASE WHEN o.is_on_time THEN 1.0 ELSE 0.0 END) * 100, 1) AS otif_pct,

    COUNT(DISTINCT i.seller_id)                      AS active_sellers,
    COUNT(DISTINCT i.seller_state)                   AS seller_states

FROM orders o
LEFT JOIN items i ON o.order_id = i.order_id
WHERE o.purchased_at IS NOT NULL
  AND i.category_en IS NOT NULL        -- exclude rows where product had no category match
GROUP BY
    DATE_TRUNC('month', o.purchased_at),
    i.category_en
ORDER BY ds, product_category