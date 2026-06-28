-- Mart: app health metrics by date x version_code x device_model x api_level x country_code.
-- Joins crash rate, ANR rate, excessive wakeup rate, and stuck bg wakelock rate
-- into a single wide table for dashboard use.
-- Slow start rate excluded (has additional start_type dimension; use stg directly for that).
-- All rate columns are 0-1 fractions from Play Console.
-- Confidence interval bounds are included only for crash rate and ANR rate
-- (the only two metric sets that return CI data from the API; verified live).
-- Full refresh each run; partitioned by date, clustered by version_code.

with crash as (
    select
        date,
        version_code,
        device_model,
        api_level,
        country_code,
        crash_rate,
        crash_rate_ci_lower,
        crash_rate_ci_upper,
        crash_rate_7d,
        crash_rate_28d
    from {{ ref('stg_play_console_crash_rate') }}
),

anr as (
    select
        date,
        version_code,
        device_model,
        api_level,
        country_code,
        anr_rate,
        anr_rate_ci_lower,
        anr_rate_ci_upper,
        anr_rate_7d,
        anr_rate_28d
    from {{ ref('stg_play_console_anr_rate') }}
),

wakelock as (
    select
        date,
        version_code,
        device_model,
        api_level,
        country_code,
        stuck_bg_wakelock_rate,
        stuck_bg_wakelock_rate_7d,
        stuck_bg_wakelock_rate_28d
    from {{ ref('stg_play_console_stuck_bg_wakelock_rate') }}
),

wakeup as (
    select
        date,
        version_code,
        device_model,
        api_level,
        country_code,
        excessive_wakeup_rate,
        excessive_wakeup_rate_7d,
        excessive_wakeup_rate_28d
    from {{ ref('stg_play_console_excessive_wakeup_rate') }}
),

joined as (
    select
        coalesce(crash.date, anr.date, wakelock.date, wakeup.date)                                     as date,
        coalesce(crash.version_code, anr.version_code, wakelock.version_code, wakeup.version_code)     as version_code,
        coalesce(crash.device_model, anr.device_model, wakelock.device_model, wakeup.device_model)     as device_model,
        coalesce(crash.api_level, anr.api_level, wakelock.api_level, wakeup.api_level)                 as api_level,
        coalesce(crash.country_code, anr.country_code, wakelock.country_code, wakeup.country_code)     as country_code,

        crash.crash_rate,
        crash.crash_rate_ci_lower,
        crash.crash_rate_ci_upper,
        crash.crash_rate_7d,
        crash.crash_rate_28d,

        anr.anr_rate,
        anr.anr_rate_ci_lower,
        anr.anr_rate_ci_upper,
        anr.anr_rate_7d,
        anr.anr_rate_28d,

        wakelock.stuck_bg_wakelock_rate,
        wakelock.stuck_bg_wakelock_rate_7d,
        wakelock.stuck_bg_wakelock_rate_28d,

        wakeup.excessive_wakeup_rate,
        wakeup.excessive_wakeup_rate_7d,
        wakeup.excessive_wakeup_rate_28d

    from crash
    full outer join anr      using (date, version_code, device_model, api_level, country_code)
    full outer join wakelock  using (date, version_code, device_model, api_level, country_code)
    full outer join wakeup    using (date, version_code, device_model, api_level, country_code)
)

select * from joined
