-- Mart: customer reviews with rating flags.
-- Grain: one row per review_id (deduped in staging).
-- Partitioned by review_date, clustered by rating.

select
    review_id,
    rating,
    title,
    body,
    reviewer_nickname,
    territory,
    created_at_ts,
    review_date,

    -- convenience flags for dashboard filtering
    rating <= 2                     as is_negative_review,

    _ingested_at,
    _source,
    _run_id

from {{ ref('stg_appstore_reviews') }}
