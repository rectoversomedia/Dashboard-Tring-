-- Staging: error count. Cast types, dedup per date x report_type x version_code x device x api_level (latest ingest).
-- countryCode not supported by errorCountMetricSet API (no countryCode dim available).
-- reportType is a required dimension for errorCountMetricSet (API constraint).
-- No confidence intervals for error count (API does not return CI for count metrics).

with source as (
    select * from {{ source('play_raw', 'raw_error_count') }}
),

typed as (
    select
        safe_cast(date as date)                             as date,
        aggregation_period,
        metric_set,
        reportType                                          as report_type,
        safe_cast(versionCode as int64)                     as version_code,
        deviceModel                                         as device_model,
        safe_cast(apiLevel as int64)                        as api_level,

        safe_cast(errorReportCount as int64)                as error_report_count,
        safe_cast(distinctUsers as int64)                   as distinct_users,

        _ingested_at,
        _source,
        _run_id,
        safe_cast(_extract_from as date)                    as _extract_from,
        safe_cast(_extract_to as date)                      as _extract_to
    from source
),

deduped as (
    select *
    from typed
    qualify row_number() over (
        partition by date, report_type, version_code, device_model, api_level
        order by _ingested_at desc
    ) = 1
)

select * from deduped
