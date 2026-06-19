-- Staging: blocked installs. Cast types, keep fraud-relevant columns.

with source as (
    select * from {{ source('appsflyer_raw', 'raw_blocked_installs') }}
),

typed as (
    select
        `AppsFlyer ID`                                      as appsflyer_id,
        safe_cast(`Install Time` as timestamp)              as install_time,
        date(safe_cast(`Install Time` as timestamp))        as install_date,
        `Media Source`                                      as media_source,
        `Campaign`                                          as campaign,
        `Campaign ID`                                       as campaign_id,
        `Country Code`                                      as country_code,
        `Platform`                                          as platform,
        `Attributed Touch Type`                             as blocked_reason,
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
        partition by appsflyer_id, install_date, _platform
        order by _ingested_at desc
    ) = 1
)

select * from deduped
