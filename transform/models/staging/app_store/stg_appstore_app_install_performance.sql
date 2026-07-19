{{
    config(
        materialized='table',
        partition_by={'field': 'date', 'data_type': 'date'},
        cluster_by=['install_status', 'territory']
    )
}}
-- Staging: app install performance. Cast types, dedup per natural key (latest ingest).

with source as (
    select * from {{ source('appstore_raw', 'raw_app_install_performance') }}
),

typed as (
    select
        safe_cast(date as date)                                 as date,
        app_name,
        app_apple_identifier,
        download_type,
        download_info,
        install_status,
        install_package_type,
        device,
        platform_version,
        territory,
        safe_cast(counts as int64)                              as counts,
        safe_cast(avg_install_duration as int64)                as avg_install_duration,

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
        partition by date, download_type, install_status, install_package_type, device, territory
        order by _ingested_at desc
    ) = 1
)

select * from deduped
