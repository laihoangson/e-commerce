-- models/silver/stg_order_items.sql
-- Order items enriched with product category (EN) and seller state.

WITH items AS (
    SELECT * FROM {{ source('bronze', 'bronze_order_items') }}
    WHERE _is_valid = TRUE
),

products AS (
    SELECT
        product_id,
        product_category_name,
        product_weight_g,
        product_length_cm,
        product_height_cm,
        product_width_cm
    FROM {{ source('bronze', 'bronze_products') }}
),

category_xlat AS (
    SELECT
        product_category_name,
        product_category_name_english
    FROM {{ source('bronze', 'bronze_category_xlat') }}
),

sellers AS (
    SELECT seller_id, seller_state, seller_city
    FROM {{ source('bronze', 'bronze_sellers') }}
)

SELECT
    i.order_id,
    i.order_item_id,
    i.product_id,
    i.seller_id,
    i.price,
    i.freight_value,
    i.price + i.freight_value AS total_item_value,

    -- Product
    COALESCE(x.product_category_name_english, p.product_category_name, 'unknown') AS category_en,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm,

    -- Derived: volumetric weight (cm³)
    COALESCE(
        p.product_length_cm * p.product_height_cm * p.product_width_cm,
        0
    ) AS volume_cm3,

    -- Seller
    s.seller_state,
    s.seller_city,

    i._ingested_at,
    i._batch_id

FROM items i
LEFT JOIN products  p ON i.product_id = p.product_id
LEFT JOIN category_xlat x ON p.product_category_name = x.product_category_name
LEFT JOIN sellers   s ON i.seller_id  = s.seller_id
