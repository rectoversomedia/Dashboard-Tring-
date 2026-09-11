-- Staging: reviews from GCS reviews/reviews_<package>_<YYYYMM>.csv.
-- Unlike raw_reviews (API), this source includes rating-only reviews -- ~55% of all
-- ratings -- and carries the real submit timestamp, not just lastModified.
-- GCS files are monthly; lag ~3-7 days.

{{
    config(
        materialized='table',
        partition_by={'field': 'review_date', 'data_type': 'date'},
        cluster_by=['star_rating']
    )
}}

with source as (
    select * from {{ source('play_raw', 'raw_gcs_reviews') }}
),

typed as (
    select
        package_name,
        device,
        reviewer_language,
        app_version_code,
        app_version_name,

        safe_cast(star_rating as int64)                                 as star_rating,
        nullif(review_title, '')                                        as review_title,
        nullif(review_text, '')                                         as review_text,

        -- submit time: the real thing, absent from the API
        safe_cast(
            review_submit_date_and_time as timestamp
        )                                                               as review_submit_at,
        date(
            safe_cast(review_submit_date_and_time as timestamp)
        )                                                               as review_date,
        safe_cast(review_submit_millis_since_epoch as int64)            as review_submit_millis,

        safe_cast(
            review_last_update_date_and_time as timestamp
        )                                                               as review_last_update_at,
        safe_cast(review_last_update_millis_since_epoch as int64)       as review_last_update_millis,

        nullif(developer_reply_text, '')                                as developer_reply_text,
        safe_cast(
            nullif(developer_reply_date_and_time, '') as timestamp
        )                                                               as developer_reply_at,

        nullif(review_link, '')                                         as review_link,

        _gcs_blob,
        _ingested_at,
        _source,
        _run_id
    from source
),

-- No review_id in this export, so the natural key is submit millis + device + rating.
-- Overlapping monthly pulls re-deliver the same rows; keep the latest ingest.
deduped as (
    select *
    from typed
    where review_date is not null
    qualify row_number() over (
        partition by review_submit_millis, device, star_rating
        order by _ingested_at desc
    ) = 1
)

select * from deduped
