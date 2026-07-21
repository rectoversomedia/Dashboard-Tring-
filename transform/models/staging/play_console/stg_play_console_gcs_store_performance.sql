-- Staging: store listing performance aggregated to daily level (all countries summed).
-- Source: GCS stats/store_performance/*_country.csv.
-- store_listing_visitors = impressions (how many users saw the listing).
-- Grain: one row per date.

{{
    config(
        materialized='table',
        partition_by={'field': 'date', 'data_type': 'date'},
        cluster_by=['date']
    )
}}

with source as (
    select * from {{ source('play_raw', 'raw_gcs_store_performance_country') }}
),

typed as (
    select
        safe_cast(date as date)                                         as date,
        package_name,
        country___region                                                as country,
        safe_cast(store_listing_acquisitions as int64)                  as store_listing_acquisitions,
        safe_cast(store_listing_visitors as int64)                      as store_listing_visitors,
        safe_cast(store_listing_conversion_rate as float64)             as store_listing_conversion_rate,

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
        partition by date, country
        order by _ingested_at desc
    ) = 1
)

select * from deduped
