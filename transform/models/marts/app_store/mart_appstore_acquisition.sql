-- Mart: daily acquisition funnel. Aggregates downloads + discovery metrics, joined by date.
-- Grain: one row per date (rolled up across territory/device/version).
-- conversion_rate = first-time downloads / impressions (null if no impressions that day).

with downloads as (
    select
        date,
        sum(case when download_type = 'First-time download' then counts else 0 end) as first_time_downloads,
        sum(case when download_type = 'Redownload' then counts else 0 end)           as redownloads,
        sum(counts)                                                                  as total_downloads
    from {{ ref('stg_appstore_app_downloads') }}
    group by date
),

-- app_units = first-time downloads + redownloads (Apple official definition)
discovery as (
    select
        date,
        sum(case when event = 'Impression' then counts else 0 end)                          as impressions,
        sum(case when event = 'Page view' and page_type = 'Product page' then counts else 0 end) as product_page_views,
        sum(case when event = 'Tap' then counts else 0 end)                                 as page_taps
    from {{ ref('stg_appstore_app_discovery_engagement') }}
    group by date
)

select
    coalesce(d.date, disc.date)                                     as date,

    coalesce(d.first_time_downloads, 0)                             as first_time_downloads,
    coalesce(d.redownloads, 0)                                      as redownloads,
    coalesce(d.first_time_downloads, 0) + coalesce(d.redownloads, 0) as app_units,
    coalesce(d.total_downloads, 0)                                  as total_downloads,

    coalesce(disc.impressions, 0)                                   as impressions,
    coalesce(disc.product_page_views, 0)                            as product_page_views,
    coalesce(disc.page_taps, 0)                                     as page_taps,

    safe_divide(
        coalesce(d.first_time_downloads, 0),
        nullif(coalesce(disc.impressions, 0), 0)
    )                                                               as conversion_rate

from downloads d
full outer join discovery disc on d.date = disc.date
