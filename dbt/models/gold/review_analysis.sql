-- Review analysis mart: score distribution and relation to delivery delay.
-- Olist has real review scores and free-text comments.
with joined as (
    select
        o.data_source,
        r.review_score,
        o.is_late
    from {{ ref('fact_reviews') }} r
    join {{ ref('fact_orders') }} o using (order_id)
)
select
    data_source,
    review_score,
    count(*)                                          as reviews,
    count(*) filter (where is_late)                   as late_delivery_reviews,
    round(avg(case when is_late then 1.0 else 0.0 end) * 100, 1) as pct_late
from joined
group by data_source, review_score
order by data_source, review_score
