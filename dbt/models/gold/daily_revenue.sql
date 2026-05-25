-- Daily revenue mart: revenue, orders, AOV per calendar day, split by data source
-- (olist = historical real, faker_live = synthetic live tail).
with order_value as (
    select
        o.order_id,
        o.data_source,
        cast(o.order_purchase_timestamp as date) as order_date,
        sum(i.item_total) as order_revenue
    from {{ ref('fact_orders') }} o
    join {{ ref('fact_order_items') }} i using (order_id)
    where o.order_status = 'delivered'
    group by o.order_id, o.data_source, cast(o.order_purchase_timestamp as date)
)
select
    order_date,
    data_source,
    count(*)                       as orders,
    round(sum(order_revenue), 2)   as revenue,
    round(avg(order_revenue), 2)   as avg_order_value
from order_value
group by order_date, data_source
order by order_date
