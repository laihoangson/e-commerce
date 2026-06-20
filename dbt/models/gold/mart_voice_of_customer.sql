-- models/gold/mart_voice_of_customer.sql
-- Reviews enriched with order context. Powers: DistilBERT training input,
-- sentiment trend chart, review score vs OTIF correlation.

WITH reviews AS (
    SELECT * FROM {{ ref('stg_reviews') }}
),

orders AS (
    SELECT * FROM {{ ref('stg_orders') }}
),

items AS (
    SELECT
        order_id,
        MODE(category_en)                  AS primary_category,
        MODE(seller_state)                 AS seller_state,
        SUM(price)                         AS order_value,
        COUNT(order_item_id)               AS item_count
    FROM {{ ref('stg_order_items') }}
    GROUP BY order_id
)

SELECT
    r.review_id,
    r.order_id,
    r.review_score,
    r.sentiment_proxy,
    r.sentiment_label,
    r.has_text,
    r.review_comment_title,
    r.review_comment_message,
    r.created_at                            AS review_created_at,

    -- Order context
    o.purchased_at,
    o.delivered_at,
    o.is_on_time,
    o.days_late,
    o.order_status,

    -- Product context
    i.primary_category,
    i.seller_state,
    ROUND(i.order_value, 2)                 AS order_value,
    i.item_count,

    -- Time features
    DATE_TRUNC('month', r.created_at)      AS review_month,
    EXTRACT(YEAR FROM r.created_at)        AS review_year,

    -- DistilBERT training label (will be overwritten by ml pipeline later)
    -- 0=negative, 1=neutral, 2=positive
    CASE r.sentiment_label
        WHEN 'negative' THEN 0
        WHEN 'neutral'  THEN 1
        WHEN 'positive' THEN 2
    END AS ml_label,

    r._batch_id

FROM reviews r
LEFT JOIN orders o ON r.order_id = o.order_id
LEFT JOIN items  i ON r.order_id = i.order_id
