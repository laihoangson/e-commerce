-- Review fact. One row per review.
select
    review_id,
    order_id,
    review_score,
    review_comment_title,
    review_comment_message,
    review_creation_date
from {{ source('bronze', 'raw_reviews') }}
where _is_valid = true
