-- Order fact. One row per order, joined to the customer's stable unique id.
-- Derives delivery delay and a late flag for downstream analytics.
with orders as (
    select *
    from {{ source('bronze', 'raw_orders') }}
    where _is_valid = true
),
cust as (
    select customer_id, customer_unique_id
    from {{ source('bronze', 'raw_customers') }}
    where _is_valid = true
)
select
    o.order_id,
    c.customer_unique_id,
    o.order_status,
    o.order_purchase_timestamp,
    o.order_approved_at,
    o.order_delivered_carrier_date,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,
    o.ab_experiment,
    o.ab_variant,
    date_diff('day', o.order_purchase_timestamp, o.order_delivered_customer_date)
        as delivery_days,
    case
        when o.order_delivered_customer_date is not null
         and o.order_delivered_customer_date > o.order_estimated_delivery_date
        then true else false
    end as is_late
from orders o
left join cust c using (customer_id)
