-- Customer LTV mart with RFM scoring, split by data source.
-- RFM quintiles are computed within each source so scores are comparable
-- inside a tab (real vs live are scored independently).
with order_value as (
    select
        o.customer_unique_id,
        o.data_source,
        o.order_id,
        cast(o.order_purchase_timestamp as date) as order_date,
        sum(i.item_total) as order_revenue
    from {{ ref('fact_orders') }} o
    join {{ ref('fact_order_items') }} i using (order_id)
    where o.order_status = 'delivered' and o.customer_unique_id is not null
    group by o.customer_unique_id, o.data_source, o.order_id,
             cast(o.order_purchase_timestamp as date)
),
rfm_base as (
    select
        customer_unique_id,
        data_source,
        date_diff('day', max(order_date),
                  max(max(order_date)) over (partition by data_source))
            as recency_days,
        count(distinct order_id)        as frequency,
        round(sum(order_revenue), 2)    as monetary
    from order_value
    group by customer_unique_id, data_source
)
select
    customer_unique_id,
    data_source,
    recency_days,
    frequency,
    monetary,
    6 - ntile(5) over (partition by data_source order by recency_days) as r_score,
    ntile(5) over (partition by data_source order by frequency)        as f_score,
    ntile(5) over (partition by data_source order by monetary)         as m_score
from rfm_base
