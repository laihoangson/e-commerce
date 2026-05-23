-- Seller dimension. One row per seller.
select
    seller_id,
    seller_postcode,
    seller_city,
    seller_state
from {{ source('bronze', 'raw_sellers') }}
where _is_valid = true
