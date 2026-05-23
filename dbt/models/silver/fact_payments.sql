-- Payment fact. One row per payment record.
select
    order_id,
    payment_sequential,
    payment_type,
    payment_installments,
    payment_value
from {{ source('bronze', 'raw_payments') }}
where _is_valid = true
