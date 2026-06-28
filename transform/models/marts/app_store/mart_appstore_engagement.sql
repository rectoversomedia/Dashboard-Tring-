-- Mart: daily engagement metrics. Combines installs/deletions with session data.
-- Grain: one row per date (rolled up across territory/device/version).

with installs as (
    select
        date,
        sum(case when event = 'Install' then counts else 0 end)         as installs,
        sum(case when event = 'Delete' then counts else 0 end)          as deletions,
        -- unique_devices on Install rows = devices with app installed that day
        sum(case when event = 'Install' then unique_devices else 0 end) as active_devices
    from {{ ref('stg_appstore_app_installs_deletions') }}
    group by date
),

sessions as (
    select
        date,
        sum(sessions)               as sessions,
        sum(total_session_duration) as total_session_duration,
        sum(unique_devices)         as unique_devices
    from {{ ref('stg_appstore_app_sessions') }}
    group by date
)

select
    coalesce(i.date, s.date)                                as date,

    coalesce(i.installs, 0)                                 as installs,
    coalesce(i.deletions, 0)                                as deletions,
    coalesce(i.active_devices, 0)                           as active_devices,

    coalesce(s.sessions, 0)                                 as sessions,
    coalesce(s.total_session_duration, 0)                   as total_session_duration,
    coalesce(s.unique_devices, 0)                           as unique_devices,

    safe_divide(
        coalesce(s.total_session_duration, 0),
        nullif(coalesce(s.sessions, 0), 0)
    )                                                       as avg_session_duration,
    safe_divide(
        coalesce(s.sessions, 0),
        nullif(coalesce(s.unique_devices, 0), 0)
    )                                                       as sessions_per_device

from installs i
full outer join sessions s on i.date = s.date
