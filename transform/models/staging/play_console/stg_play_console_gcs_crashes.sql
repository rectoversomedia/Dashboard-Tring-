-- Staging: daily absolute crash/ANR counts from GCS stats/crashes/*_overview.csv.
-- Complements crashRateMetricSet (which gives rate); this gives raw daily count.
-- Grain: one row per date (deduped by latest ingest).

{{
    config(
        materialized='table',
        partition_by={'field': 'date', 'data_type': 'date'},
        cluster_by=['date']
    )
}}

with source as (
    select * from {{ source('play_raw', 'raw_gcs_crashes') }}
),

typed as (
    select
        safe_cast(date as date)                     as date,
        package_name,
        safe_cast(daily_crashes as int64)           as daily_crashes,
        safe_cast(daily_anrs as int64)              as daily_anrs,

        _ingested_at,
        _source,
        _run_id,
        safe_cast(_extract_from as date)            as _extract_from,
        safe_cast(_extract_to as date)              as _extract_to
    from source
),

deduped as (
    select *
    from typed
    qualify row_number() over (
        partition by date
        order by _ingested_at desc
    ) = 1
)

select * from deduped
