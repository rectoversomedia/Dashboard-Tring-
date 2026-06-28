-- Staging: app sessions. Cast types, dedup per natural key (latest ingest).

with source as (
    select * from {{ source('appstore_raw', 'raw_app_sessions') }}
),

typed as (
    select
        safe_cast(date as date)                                 as date,
        app_name,
        app_apple_identifier,
        app_version,
        device,
        platform_version,
        source_type,
        page_type,
        app_download_date,
        territory,
        safe_cast(sessions as int64)                            as sessions,
        safe_cast(total_session_duration as int64)              as total_session_duration,
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
        partition by date, app_version, device, source_type, territory
        order by _ingested_at desc
    ) = 1
)

select * from deduped
