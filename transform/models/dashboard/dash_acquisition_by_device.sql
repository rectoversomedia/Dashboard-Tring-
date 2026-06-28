-- Dashboard: sessions/installs per device model per day, both platforms.
-- Android: device_model from mart_play_console_app_health (crash/ANR by device, no install count).
-- iOS: device family from stg_appstore_app_sessions (sessions per device).
-- Grain: one row per platform x device x date.

with android as (
    select
        'android'               as platform,
        date,
        device_model            as device,
        avg(crash_rate)         as avg_crash_rate,
        avg(anr_rate)           as avg_anr_rate,
        cast(null as int64)     as sessions,
        cast(null as int64)     as unique_devices,
        count(*)                as data_points
    from {{ ref('mart_play_console_app_health') }}
    where device_model is not null
    group by date, device_model
),

ios as (
    select
        'ios'                       as platform,
        date,
        device,
        cast(null as float64)       as avg_crash_rate,
        cast(null as float64)       as avg_anr_rate,
        sum(sessions)               as sessions,
        sum(unique_devices)         as unique_devices,
        count(*)                    as data_points
    from {{ ref('stg_appstore_app_sessions') }}
    where device is not null
    group by date, device
)

select * from android
union all
select * from ios
