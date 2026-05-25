-- Funnel conversion mart by lifecycle stage, split by data source.
select
    data_source,
    count(*)                                                          as purchased,
    count(*) filter (where order_approved_at is not null)             as approved,
    count(*) filter (where order_delivered_carrier_date is not null)  as shipped,
    count(*) filter (where order_delivered_customer_date is not null) as delivered,
    round(100.0 * count(*) filter (where order_delivered_customer_date is not null)
          / nullif(count(*), 0), 1)                                   as delivery_rate_pct
from {{ ref('fact_orders') }}
group by data_source
