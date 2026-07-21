-- Staging: daily installs/uninstalls from GCS stats/installs/*_overview.csv.
-- GCS files are monthly; lag ~3-7 days. One row per date (deduped by latest ingest).

{{
    config(
        materialized='table',
        partition_by={'field': 'date', 'data_type': 'date'},
        cluster_by=['date']
    )
}}

with source as (
    select * from {{ source('play_raw', 'raw_gcs_installs') }}
),

typed as (
    select
        safe_cast(date as date)                                         as date,
        package_name,

        safe_cast(daily_device_installs as int64)                       as daily_device_installs,
        safe_cast(daily_device_uninstalls as int64)                     as daily_device_uninstalls,
        safe_cast(daily_device_upgrades as int64)                       as daily_device_upgrades,
        safe_cast(total_user_installs as int64)                         as total_user_installs,
        safe_cast(daily_user_installs as int64)                         as daily_user_installs,
        safe_cast(daily_user_uninstalls as int64)                       as daily_user_uninstalls,
        safe_cast(active_device_installs as int64)                      as active_device_installs,
        safe_cast(install_events as int64)                              as install_events,
        safe_cast(update_events as int64)                               as update_events,
        safe_cast(uninstall_events as int64)                            as uninstall_events,

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
        partition by date
        order by _ingested_at desc
    ) = 1
)

select * from deduped
