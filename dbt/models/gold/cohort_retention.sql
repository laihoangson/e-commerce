-- Cohort retention mart: customers grouped by first-purchase month, with the
-- count active in each subsequent month offset.
with first_order as (
    select
        customer_unique_id,
        date_trunc('month', min(order_purchase_timestamp)) as cohort_month
    from {{ ref('fact_orders') }}
    where customer_unique_id is not null
    group by customer_unique_id
),
activity as (
    select distinct
        o.customer_unique_id,
        date_trunc('month', o.order_purchase_timestamp) as activity_month
    from {{ ref('fact_orders') }} o
    where o.customer_unique_id is not null
)
select
    f.cohort_month,
    date_diff('month', f.cohort_month, a.activity_month) as month_offset,
    count(distinct f.customer_unique_id) as active_customers
from first_order f
join activity a using (customer_unique_id)
group by f.cohort_month, month_offset
order by f.cohort_month, month_offset
