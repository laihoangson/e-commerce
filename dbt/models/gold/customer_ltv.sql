-- Customer LTV mart with RFM (Recency, Frequency, Monetary) scoring.
with order_value as (
    select
        o.customer_unique_id,
        o.order_id,
        cast(o.order_purchase_timestamp as date) as order_date,
        sum(i.item_total) as order_revenue
    from {{ ref('fact_orders') }} o
    join {{ ref('fact_order_items') }} i using (order_id)
    where o.order_status = 'delivered' and o.customer_unique_id is not null
    group by o.customer_unique_id, o.order_id, cast(o.order_purchase_timestamp as date)
),
rfm_base as (
    select
        customer_unique_id,
        date_diff('day', max(order_date), (select max(order_date) from order_value))
            as recency_days,
        count(distinct order_id)        as frequency,
        round(sum(order_revenue), 2)    as monetary
    from order_value
    group by customer_unique_id
)
select
    customer_unique_id,
    recency_days,
    frequency,
    monetary,
    -- RFM quintile scores (5 = best). Recency reversed (lower days = better).
    6 - ntile(5) over (order by recency_days)  as r_score,
    ntile(5) over (order by frequency)         as f_score,
    ntile(5) over (order by monetary)          as m_score
from rfm_base
