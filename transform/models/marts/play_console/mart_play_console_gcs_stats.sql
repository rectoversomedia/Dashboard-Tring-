-- Mart: daily Android acquisition + crash counts from GCS bucket exports.
-- Fills the gap not covered by Play Developer Reporting REST API:
-- installs, uninstalls, store impressions, absolute crash/ANR counts.
-- Grain: one row per date.

{{
    config(
        materialized='table',
        partition_by={'field': 'date', 'data_type': 'date'},
        cluster_by=['date']
    )
}}

with installs as (
    select
        date,
        daily_device_installs,
        daily_device_uninstalls,
        daily_device_upgrades,
        active_device_installs,
        install_events,
        uninstall_events
    from {{ ref('stg_play_console_gcs_installs') }}
),

impressions as (
    select
        date,
        sum(store_listing_visitors)     as store_listing_impressions,
        sum(store_listing_acquisitions) as store_listing_acquisitions,
        safe_divide(
            sum(store_listing_acquisitions),
            nullif(sum(store_listing_visitors), 0)
        )                               as store_listing_conversion_rate
    from {{ ref('stg_play_console_gcs_store_performance') }}
    group by date
),

crashes as (
    select
        date,
        daily_crashes,
        daily_anrs
    from {{ ref('stg_play_console_gcs_crashes') }}
)

select
    coalesce(i.date, imp.date, c.date)  as date,
    'android'                           as platform,

    i.daily_device_installs,
    i.daily_device_uninstalls,
    i.daily_device_upgrades,
    i.active_device_installs,
    i.install_events,
    i.uninstall_events,

    imp.store_listing_impressions,
    imp.store_listing_acquisitions,
    imp.store_listing_conversion_rate,

    c.daily_crashes,
    c.daily_anrs

from installs i
full outer join impressions imp on i.date = imp.date
full outer join crashes c on coalesce(i.date, imp.date) = c.date
