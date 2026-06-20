-- models/silver/stg_reviews.sql
-- Cleaned reviews. Adds a simple numeric sentiment proxy (1-5 → -1 to +1)
-- for use before DistilBERT is trained. Will be replaced by ml_sentiment later.

WITH raw AS (
    SELECT * FROM {{ source('bronze', 'bronze_reviews') }}
    WHERE _is_valid = TRUE
)

SELECT
    review_id,
    order_id,
    review_score,

    -- Map 1-5 stars → [-1, +1] sentiment proxy
    ROUND((CAST(review_score AS DOUBLE) - 3.0) / 2.0, 2) AS sentiment_proxy,

    -- Positive / neutral / negative bucket
    CASE
        WHEN review_score >= 4 THEN 'positive'
        WHEN review_score = 3  THEN 'neutral'
        ELSE 'negative'
    END AS sentiment_label,

    review_comment_title,
    review_comment_message,

    -- Has text content
    CASE WHEN LENGTH(COALESCE(review_comment_message, '')) > 10
         THEN TRUE ELSE FALSE END AS has_text,

    CAST(review_creation_date     AS TIMESTAMP) AS created_at,
    CAST(review_answer_timestamp  AS TIMESTAMP) AS answered_at,

    _ingested_at,
    _batch_id

FROM raw
WHERE review_score IS NOT NULL
