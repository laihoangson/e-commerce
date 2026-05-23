-- Product dimension. One row per product.
select
    product_id,
    product_category_name,
    product_weight_g,
    product_length_cm,
    product_height_cm,
    product_width_cm,
    base_price
from {{ source('bronze', 'raw_products') }}
where _is_valid = true
