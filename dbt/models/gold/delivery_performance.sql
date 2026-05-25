-- Delivery performance mart: on-time vs late, avg delivery days, by data source.
-- Leverages Olist's rich lifecycle timestamps.
with delivered as (
    select
        data_source,
        delivery_days,
        is_late
    from {{ ref('fact_orders') }}
    where order_status = 'delivered'
      and order_delivered_customer_date is not null
      and delivery_days is not null
      and delivery_days >= 0
)
select
    data_source,
    count(*)                                            as delivered_orders,
    round(avg(delivery_days), 1)                        as avg_delivery_days,
    count(*) filter (where is_late)                     as late_orders,
    round(100.0 * count(*) filter (where is_late)
          / nullif(count(*), 0), 1)                     as late_rate_pct
from delivered
group by data_source
