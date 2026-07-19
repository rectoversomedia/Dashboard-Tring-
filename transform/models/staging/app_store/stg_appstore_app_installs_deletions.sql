{{
    config(
        materialized='table',
        partition_by={'field': 'date', 'data_type': 'date'},
        cluster_by=['event', 'territory']
    )
}}
-- Staging: app installs and deletions. Cast types, dedup per natural key (latest ingest).
-- event values: 'Install' or 'Delete' (Apple API enum).

with source as (
    select * from {{ source('appstore_raw', 'raw_app_installs_deletions') }}
),

typed as (
    select
        safe_cast(date as date)                                 as date,
        app_name,
        app_apple_identifier,
        event,
        download_type,
        app_version,
        device,
        platform_version,
        source_type,
        page_type,
        app_download_date,
        territory,
        safe_cast(counts as int64)                              as counts,
        safe_cast(unique_devices as int64)                      as unique_devices,

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
        partition by date, event, download_type, app_version, device, source_type, territory
        order by _ingested_at desc
    ) = 1
)

select * from deduped
