-- Staging: campaign stats. Cast types, dedup to one row per campaign_id x platform x date (latest ingest).
-- Raw stores all source fields as STRING. platform comes from _flatten_stats output (ANDROID/IOS/UNKNOWN).
-- delivery_funnel and conversion_goal_stats are Python str(dict) -- kept as strings.

with source as (
    select * from {{ source('moengage_raw', 'raw_campaign_stats') }}
),

typed as (
    select
        campaign_id,
        platform,
        locale,
        variation,

        -- performance_stats fields
        safe_cast(sent as int64)                as sent,
        safe_cast(impression as int64)          as impression,
        safe_cast(click as int64)               as click,
        safe_cast(ctr as float64)               as ctr,
        safe_cast(attempted as int64)           as attempted,
        safe_cast(failed as int64)              as failed,
        safe_cast(device_start as int64)        as device_start,
        safe_cast(delivery_rate as float64)     as delivery_rate,
        safe_cast(sent_rate as float64)         as sent_rate,
        safe_cast(failure_rate as float64)      as failure_rate,

        -- nested fields kept as strings
        delivery_funnel,
        conversion_goal_stats,

        _ingested_at,
        _source,
        _run_id,
        safe_cast(_extract_from as date)        as _extract_from,
        safe_cast(_extract_to as date)          as _extract_to,
        _schema_flag
    from source
),

deduped as (
    select *
    from typed
    qualify row_number() over (
        partition by campaign_id, platform, locale, variation, _extract_from
        order by _ingested_at desc
    ) = 1
)

select * from deduped
