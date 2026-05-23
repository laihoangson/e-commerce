-- Date dimension spanning the order history plus headroom for live mode.
-- Generated from a date range; one row per calendar day.
with bounds as (
    select
        date_trunc('day', min(order_purchase_timestamp)) as min_d,
        date_trunc('day', max(order_purchase_timestamp)) as max_d
    from {{ source('bronze', 'raw_orders') }}
    where _is_valid = true
),
spine as (
    select unnest(
        range(
            (select min_d from bounds),
            (select max_d from bounds) + interval '1 day',
            interval '1 day'
        )
    ) as date_day
)
select
    cast(date_day as date)                       as date_day,
    extract(year   from date_day)                as year,
    extract(month  from date_day)                as month,
    extract(day    from date_day)                as day,
    extract(dow    from date_day)                as day_of_week,
    extract(week   from date_day)                as week_of_year,
    extract(quarter from date_day)               as quarter,
    case when extract(dow from date_day) in (0, 6)
         then true else false end                as is_weekend
from spine
