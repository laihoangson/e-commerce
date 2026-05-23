-- A/B test results mart: per experiment/variant, conversion and AOV metrics
-- for the Phase 5 statistical engine to consume.
with order_value as (
    select
        o.order_id,
        o.ab_experiment,
        o.ab_variant,
        o.order_status,
        sum(i.item_total) as order_revenue
    from {{ ref('fact_orders') }} o
    join {{ ref('fact_order_items') }} i using (order_id)
    where o.ab_experiment is not null
    group by o.order_id, o.ab_experiment, o.ab_variant, o.order_status
)
select
    ab_experiment,
    ab_variant,
    count(*)                                                   as orders,
    count(*) filter (where order_status = 'delivered')         as delivered_orders,
    round(avg(order_revenue), 2)                               as avg_order_value,
    round(sum(order_revenue), 2)                               as total_revenue
from order_value
group by ab_experiment, ab_variant
order by ab_experiment, ab_variant
