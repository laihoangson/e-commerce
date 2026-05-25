-- Revenue and orders by Brazilian state, for the choropleth map.
-- Joins orders to the customer's state via dim_customers.
with order_value as (
    select
        o.order_id,
        o.data_source,
        o.customer_unique_id,
        sum(i.item_total) as order_revenue
    from {{ ref('fact_orders') }} o
    join {{ ref('fact_order_items') }} i using (order_id)
    where o.order_status = 'delivered'
    group by o.order_id, o.data_source, o.customer_unique_id
)
select
    c.customer_state as state,
    ov.data_source,
    count(*)                       as orders,
    round(sum(ov.order_revenue), 2) as revenue
from order_value ov
join {{ ref('dim_customers') }} c using (customer_unique_id)
where c.customer_state is not null
group by c.customer_state, ov.data_source
order by revenue desc
