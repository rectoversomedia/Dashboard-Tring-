-- Staging: slow start rate. Cast types, dedup per date x version_code x start_type (latest ingest).
-- startType dimension distinguishes cold/warm/hot starts.
-- Data lags 2-3 days from Play Console (API constraint, not a pipeline bug).

with source as (
    select * from {{ source('play_raw', 'raw_slow_start_rate') }}
),

typed as (
    select
        safe_cast(date as date)                                     as date,
        aggregation_period,
        metric_set,
        safe_cast(versionCode as int64)                             as version_code,
        startType                                                   as start_type,

        safe_cast(slowStartRate as float64)                         as slow_start_rate,
        safe_cast(slowStartRate7dUserWeighted as float64)           as slow_start_rate_7d,
        safe_cast(slowStartRate28dUserWeighted as float64)          as slow_start_rate_28d,

        _ingested_at,
        _source,
        _run_id,
        safe_cast(_extract_from as date)                            as _extract_from,
        safe_cast(_extract_to as date)                              as _extract_to
    from source
),

deduped as (
    select *
    from typed
    qualify row_number() over (
        partition by date, version_code, start_type
        order by _ingested_at desc
    ) = 1
)

select * from deduped
