-- Cohort retention mart: customers grouped by first-purchase month, with the
-- count active in each subsequent month offset. Split by data source so the
-- real (Olist) and live (synthetic) tabs show their own cohorts.
with first_order as (
    select
        customer_unique_id,
        data_source,
        date_trunc('month', min(order_purchase_timestamp)) as cohort_month
    from {{ ref('fact_orders') }}
    where customer_unique_id is not null
    group by customer_unique_id, data_source
),
activity as (
    select distinct
        o.customer_unique_id,
        o.data_source,
        date_trunc('month', o.order_purchase_timestamp) as activity_month
    from {{ ref('fact_orders') }} o
    where o.customer_unique_id is not null
)
select
    f.data_source,
    f.cohort_month,
    date_diff('month', f.cohort_month, a.activity_month) as month_offset,
    count(distinct f.customer_unique_id) as active_customers
from first_order f
join activity a
    on f.customer_unique_id = a.customer_unique_id
   and f.data_source = a.data_source
group by f.data_source, f.cohort_month, month_offset
order by f.cohort_month, month_offset
