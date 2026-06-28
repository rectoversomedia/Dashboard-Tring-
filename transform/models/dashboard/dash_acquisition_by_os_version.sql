-- Dashboard: sessions / health metrics per OS version per day.
-- Android: api_level from mart_play_console_app_health (e.g. 33 = Android 13).
-- iOS: not available (Apple Analytics API does not return iOS version in ingested reports).
-- Grain: one row per platform x os_version x date.

select
    'android'           as platform,
    date,
    cast(api_level as string) as os_version,
    -- no install count available via REST API; health metrics only
    avg(crash_rate)     as avg_crash_rate,
    avg(anr_rate)       as avg_anr_rate,
    count(*)            as data_points
from {{ ref('mart_play_console_app_health') }}
where api_level is not null
group by date, api_level
