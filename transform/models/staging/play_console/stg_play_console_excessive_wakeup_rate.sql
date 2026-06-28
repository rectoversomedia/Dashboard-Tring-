-- Staging: excessive wakeup rate. Cast types, dedup per date x version_code x device x api_level x country (latest ingest).
-- Data lags 2-3 days from Play Console (API constraint, not a pipeline bug).

with source as (
    select * from {{ source('play_raw', 'raw_excessive_wakeup_rate') }}
),

typed as (
    select
        safe_cast(date as date)                                         as date,
        aggregation_period,
        metric_set,
        safe_cast(versionCode as int64)                                 as version_code,
        deviceModel                                                     as device_model,
        safe_cast(apiLevel as int64)                                    as api_level,
        countryCode                                                     as country_code,

        safe_cast(excessiveWakeupRate as float64)                       as excessive_wakeup_rate,
        safe_cast(excessiveWakeupRate7dUserWeighted as float64)         as excessive_wakeup_rate_7d,
        safe_cast(excessiveWakeupRate28dUserWeighted as float64)        as excessive_wakeup_rate_28d,

        _ingested_at,
        _source,
        _run_id,
        safe_cast(_extract_from as date)                                as _extract_from,
        safe_cast(_extract_to as date)                                  as _extract_to
    from source
),

deduped as (
    select *
    from typed
    qualify row_number() over (
        partition by date, version_code, device_model, api_level, country_code
        order by _ingested_at desc
    ) = 1
)

select * from deduped
