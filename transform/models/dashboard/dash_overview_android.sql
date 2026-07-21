-- Dashboard: Android KPIs per day. Aggregated across all versions/devices.
-- Sources: mart_play_console_app_health (health) + mart_play_console_reviews (rating)
--          + mart_play_console_gcs_stats (installs/uninstalls/impressions from GCS).
-- Grain: one row per date.

with health as (
    select
        date,
        avg(crash_rate)                 as avg_crash_rate,
        avg(anr_rate)                   as avg_anr_rate,
        avg(excessive_wakeup_rate)      as avg_excessive_wakeup_rate,
        avg(stuck_bg_wakelock_rate)     as avg_stuck_bg_wakelock_rate
    from {{ ref('mart_play_console_app_health') }}
    group by date
),

ratings as (
    select
        review_date                         as date,
        count(*)                            as total_reviews,
        avg(cast(star_rating as float64))   as avg_rating,
        countif(star_rating <= 2)           as negative_reviews
    from {{ ref('mart_play_console_reviews') }}
    group by review_date
),

gcs as (
    select
        date,
        daily_device_installs,
        daily_device_uninstalls,
        store_listing_impressions,
        store_listing_conversion_rate,
        daily_crashes                   as daily_crash_count,
        daily_anrs                      as daily_anr_count
    from {{ ref('mart_play_console_gcs_stats') }}
)

select
    coalesce(h.date, r.date, g.date)        as date,
    'android'                               as platform,

    -- health metrics (rate-based, from REST API)
    h.avg_crash_rate,
    h.avg_anr_rate,
    h.avg_excessive_wakeup_rate,
    h.avg_stuck_bg_wakelock_rate,

    -- ratings
    coalesce(r.total_reviews, 0)            as total_reviews,
    r.avg_rating,
    coalesce(r.negative_reviews, 0)         as negative_reviews,

    -- acquisition (from GCS)
    g.daily_device_installs,
    g.daily_device_uninstalls,
    g.store_listing_impressions,
    g.store_listing_conversion_rate,

    -- absolute crash counts (from GCS)
    g.daily_crash_count,
    g.daily_anr_count

from health h
full outer join ratings r on h.date = r.date
full outer join gcs g on coalesce(h.date, r.date) = g.date
