-- Mart: complete Android review/rating history from GCS exports.
-- Grain: one row per review (submit millis x device x star rating).
--
-- Use this instead of mart_play_console_reviews for rating metrics: the API-backed
-- mart only sees comment-bearing reviews (~45%), which drags avg_rating down by
-- roughly a full star. This source has both, plus the true submit date.

select
    review_date,
    'android'                                       as platform,

    star_rating,
    review_title,
    review_text,
    review_text is not null                         as has_review_text,

    device,
    reviewer_language,
    app_version_code,
    app_version_name,

    review_submit_at,
    review_last_update_at,

    developer_reply_text,
    developer_reply_at,
    developer_reply_text is not null                as has_developer_reply,

    star_rating <= 2                                as is_negative_review,
    star_rating >= 4                                as is_positive_review,

    review_link,
    _ingested_at,
    _source

from {{ ref('stg_play_console_gcs_reviews') }}
