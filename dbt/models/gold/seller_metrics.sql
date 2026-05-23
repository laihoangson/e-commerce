-- Seller metrics mart: volume, revenue, avg review score per seller.
with seller_orders as (
    select
        i.seller_id,
        i.order_id,
        sum(i.item_total) as order_revenue
    from {{ ref('fact_order_items') }} i
    group by i.seller_id, i.order_id
),
seller_reviews as (
    select
        i.seller_id,
        avg(r.review_score) as avg_review_score
    from {{ ref('fact_order_items') }} i
    join {{ ref('fact_reviews') }} r using (order_id)
    group by i.seller_id
)
select
    so.seller_id,
    s.seller_state,
    count(distinct so.order_id)        as total_orders,
    round(sum(so.order_revenue), 2)    as total_revenue,
    round(coalesce(sr.avg_review_score, 0), 2) as avg_review_score
from seller_orders so
left join {{ ref('dim_sellers') }} s on so.seller_id = s.seller_id
left join seller_reviews sr on so.seller_id = sr.seller_id
group by so.seller_id, s.seller_state, sr.avg_review_score
order by total_revenue desc
