-- Geography dimension. One row per postcode.
select
    geolocation_postcode as postcode,
    any_value(geolocation_lat)   as lat,
    any_value(geolocation_lng)   as lng,
    any_value(geolocation_city)  as city,
    any_value(geolocation_state) as state
from {{ source('bronze', 'raw_geolocation') }}
where _is_valid = true
group by geolocation_postcode
