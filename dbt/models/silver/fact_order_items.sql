-- Order item fact. One row per item line.
select
    order_id,
    order_item_id,
    product_id,
    seller_id,
    price,
    freight_value,
    price + freight_value as item_total
from {{ source('bronze', 'raw_order_items') }}
where _is_valid = true
