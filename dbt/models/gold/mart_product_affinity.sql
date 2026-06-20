-- models/gold/mart_product_affinity.sql
-- One row per order, with category basket (array-like via string_agg).
-- Also produces category co-occurrence counts for Apriori pre-computation.

WITH order_categories AS (
    SELECT
        order_id,
        -- Sorted, comma-joined category list per order (basket)
        STRING_AGG(DISTINCT category_en ORDER BY category_en) AS basket,
        COUNT(DISTINCT category_en)                           AS basket_size,
        COUNT(order_item_id)                                  AS item_count,
        SUM(price)                                            AS basket_value
    FROM {{ ref('stg_order_items') }}
    GROUP BY order_id
),

-- Category pair co-occurrence (for association rules pre-computation)
cat_pairs AS (
    SELECT
        a.category_en  AS cat_a,
        b.category_en  AS cat_b,
        COUNT(DISTINCT a.order_id) AS co_occurrence_count
    FROM {{ ref('stg_order_items') }} a
    JOIN {{ ref('stg_order_items') }} b
        ON  a.order_id    = b.order_id
        AND a.category_en < b.category_en   -- avoid duplicates and self-joins
    GROUP BY a.category_en, b.category_en
    HAVING COUNT(DISTINCT a.order_id) >= 10  -- minimum support filter
)

-- Primary output: basket per order (used as mlxtend TransactionEncoder input)
SELECT
    oc.order_id,
    oc.basket,
    oc.basket_size,
    oc.item_count,
    ROUND(oc.basket_value, 2) AS basket_value
FROM order_categories oc
WHERE oc.basket_size >= 1
ORDER BY oc.basket_value DESC
