-- Dashboard: iOS downloads + sessions per app_version per day.
-- Grain: one row per date x app_version.
-- Note: Android install count per version is not available via Play Console REST API.
-- Android appears here only via crash_rate/anr_rate from mart_play_console_app_health (different grain).
-- This model covers iOS only (source: stg_appstore staging views).

with downloads as (
    select
        date,
        app_version,
        sum(case when download_type = 'First-time download' then counts else 0 end) as first_time_downloads,
        sum(case when download_type = 'Redownload' then counts else 0 end)           as redownloads,
        sum(counts)                                                                  as total_downloads
    from {{ ref('stg_appstore_app_downloads') }}
    group by date, app_version
),

sessions as (
    select
        date,
        app_version,
        sum(sessions)               as sessions,
        sum(unique_devices)         as unique_devices,
        sum(total_session_duration) as total_session_duration
    from {{ ref('stg_appstore_app_sessions') }}
    group by date, app_version
)

select
    'ios'                                               as platform,
    coalesce(d.date, s.date)                            as date,
    coalesce(d.app_version, s.app_version)              as app_version,

    coalesce(d.first_time_downloads, 0)                 as first_time_downloads,
    coalesce(d.redownloads, 0)                          as redownloads,
    coalesce(d.total_downloads, 0)                      as total_downloads,

    coalesce(s.sessions, 0)                             as sessions,
    coalesce(s.unique_devices, 0)                       as unique_devices,
    coalesce(s.total_session_duration, 0)               as total_session_duration

from downloads d
full outer join sessions s using (date, app_version)
