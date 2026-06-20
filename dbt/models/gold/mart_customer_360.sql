-- models/gold/mart_customer_360.sql
-- Customer-level aggregates + Seller scorecard.
-- Powers: K-Means segmentation, customer LTV chart, seller leaderboard.

WITH orders AS (
    SELECT * FROM {{ ref('stg_orders') }}
),

items AS (
    SELECT * FROM {{ ref('stg_order_items') }}
),

reviews AS (
    SELECT * FROM {{ ref('stg_reviews') }}
),

-- ── Customer aggregates ───────────────────────────────────────────────────
cust_orders AS (
    SELECT
        o.customer_id,
        COUNT(DISTINCT o.order_id)                          AS total_orders,
        SUM(i.price)                                        AS total_gmv,
        AVG(i.price)                                        AS avg_order_value,
        MIN(o.purchased_at)                                 AS first_order_at,
        MAX(o.purchased_at)                                 AS last_order_at,
        DATE_DIFF('day', MIN(o.purchased_at),
                          MAX(o.purchased_at))              AS customer_age_days,

        -- Recency: days since last order (relative to dataset max)
        DATE_DIFF('day', MAX(o.purchased_at),
            (SELECT MAX(purchased_at) FROM orders))         AS recency_days,

        -- OTIF rate
        AVG(CASE WHEN o.is_on_time THEN 1.0 ELSE 0.0 END)  AS otif_rate,

        -- Review score avg
        AVG(r.review_score)                                 AS avg_review_score

    FROM orders o
    LEFT JOIN items   i ON o.order_id  = i.order_id
    LEFT JOIN reviews r ON o.order_id  = r.order_id
    GROUP BY o.customer_id
),

cust_raw AS (
    SELECT customer_id, customer_state, customer_city, customer_zip_code_prefix
    FROM {{ source('bronze', 'bronze_customers') }}
)

SELECT
    co.customer_id,
    cr.customer_state,
    cr.customer_city,
    co.total_orders,
    ROUND(co.total_gmv, 2)        AS total_gmv,
    ROUND(co.avg_order_value, 2)  AS avg_order_value,
    co.first_order_at,
    co.last_order_at,
    co.customer_age_days,
    co.recency_days,
    ROUND(co.otif_rate * 100, 1)  AS otif_pct,
    ROUND(co.avg_review_score, 2) AS avg_review_score,

    -- RFM buckets (pre-computed for K-Means feature input)
    NTILE(5) OVER (ORDER BY co.recency_days DESC)     AS r_score,   -- 5=most recent
    NTILE(5) OVER (ORDER BY co.total_orders ASC)      AS f_score,   -- 5=most frequent
    NTILE(5) OVER (ORDER BY co.total_gmv ASC)         AS m_score    -- 5=highest spend

FROM cust_orders co
LEFT JOIN cust_raw cr ON co.customer_id = cr.customer_id
