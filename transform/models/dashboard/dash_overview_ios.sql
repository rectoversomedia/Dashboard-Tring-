-- Dashboard: iOS KPIs per day. Aggregated across all territories/devices.
-- Sources: mart_appstore_acquisition + mart_appstore_engagement + mart_appstore_reviews.
-- Grain: one row per date.

with acquisition as (
    select
        date,
        first_time_downloads,
        redownloads,
        app_units,
        total_downloads,
        impressions,
        product_page_views,
        conversion_rate
    from {{ ref('mart_appstore_acquisition') }}
),

engagement as (
    select
        date,
        installs,
        deletions,
        sessions,
        avg_session_duration,
        unique_devices
    from {{ ref('mart_appstore_engagement') }}
),

ratings as (
    select
        review_date                                 as date,
        count(*)                                    as total_reviews,
        avg(safe_cast(rating as float64))           as avg_rating,
        countif(safe_cast(rating as int64) <= 2)    as negative_reviews
    from {{ ref('mart_appstore_reviews') }}
    group by review_date
)

select
    coalesce(a.date, e.date, r.date)        as date,
    'ios'                                   as platform,

    -- acquisition
    coalesce(a.first_time_downloads, 0)     as first_time_downloads,
    coalesce(a.redownloads, 0)              as redownloads,
    coalesce(a.app_units, 0)               as app_units,
    coalesce(a.impressions, 0)              as impressions,
    coalesce(a.product_page_views, 0)       as product_page_views,
    a.conversion_rate,

    -- engagement
    coalesce(e.installs, 0)                 as installs,
    coalesce(e.deletions, 0)               as deletions,
    e.installs - e.deletions               as net_installs,
    coalesce(e.sessions, 0)               as sessions,
    e.avg_session_duration,
    coalesce(e.unique_devices, 0)          as unique_devices,

    -- ratings
    coalesce(r.total_reviews, 0)           as total_reviews,
    r.avg_rating,
    coalesce(r.negative_reviews, 0)        as negative_reviews

from acquisition a
full outer join engagement e on a.date = e.date
full outer join ratings r on coalesce(a.date, e.date) = r.date
