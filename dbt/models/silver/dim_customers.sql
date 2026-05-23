-- Customer dimension keyed by the stable customer_unique_id.
-- Bronze has one row per order; we collapse to one row per unique customer.
with valid as (
    select *
    from {{ source('bronze', 'raw_customers') }}
    where _is_valid = true
)
select
    customer_unique_id,
    any_value(customer_postcode) as customer_postcode,
    any_value(customer_city)     as customer_city,
    any_value(customer_state)    as customer_state,
    count(*)                     as order_count
from valid
group by customer_unique_id
