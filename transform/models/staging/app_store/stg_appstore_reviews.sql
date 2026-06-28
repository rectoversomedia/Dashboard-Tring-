-- Staging: customer reviews. Cast types, dedup to one row per review_id (latest ingest).
-- Apple returns all reviews since app launch; staging keeps the freshest copy of each review.

with source as (
    select * from {{ source('appstore_raw', 'raw_reviews') }}
),

typed as (
    select
        review_id,
        safe_cast(rating as int64)                              as rating,
        title,
        body,
        reviewer_nickname,
        territory,

        -- iso8601 timestamp with offset; cast for consistent ts arithmetic downstream
        safe_cast(created_date as timestamp)                    as created_at_ts,
        date(safe_cast(created_date as timestamp))              as review_date,

        _ingested_at,
        _source,
        _run_id,
        safe_cast(_extract_from as date)                        as _extract_from,
        safe_cast(_extract_to as date)                          as _extract_to
    from source
),

deduped as (
    select *
    from typed
    qualify row_number() over (
        partition by review_id
        order by _ingested_at desc
    ) = 1
)

select * from deduped
