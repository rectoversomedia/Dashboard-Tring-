-- Staging: campaign performance from master-agg-data. Cast types, keep KPI columns.

with source as (
    select * from {{ source('appsflyer_raw', 'raw_campaign_performance') }}
),

typed as (
    select
        date(safe_cast(`Install Time` as timestamp))    as date,
        `Media Source`                                  as media_source,
        `Campaign`                                      as campaign,
        `GEO`                                           as country_code,
        safe_cast(`Impressions` as int64)           as impressions,
        safe_cast(`Clicks` as int64)                as clicks,
        safe_cast(`Installs` as int64)              as installs,
        safe_cast(`Cost` as float64)                as cost,
        _platform,
        _app_id,
        _ingested_at,
        _run_id,
        _extract_from,
        _extract_to,
        _schema_flag
    from source
),

deduped as (
    select *
    from typed
    qualify row_number() over (
        partition by date, media_source, campaign, country_code, _platform
        order by _ingested_at desc
    ) = 1
)

select * from deduped
