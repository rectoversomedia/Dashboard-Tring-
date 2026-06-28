-- Staging: app store discovery and engagement. Cast types, dedup per natural key (latest ingest).
-- event values: 'Impression', 'Page view', 'Tap' (Apple API enum).

with source as (
    select * from {{ source('appstore_raw', 'raw_app_discovery_engagement') }}
),

typed as (
    select
        safe_cast(date as date)                                 as date,
        app_name,
        app_apple_identifier,
        event,
        page_type,
        source_type,
        engagement_type,
        device,
        platform_version,
        territory,
        safe_cast(counts as int64)                              as counts,
        safe_cast(unique_counts as int64)                       as unique_counts,

        _ingested_at,
        _source,
        _run_id,
        safe_cast(_extract_from as date)                        as _extract_from,
        safe_cast(_extract_to as date)                          as _extract_to
    from source
),

deduped as (
    select *
    from typed
    qualify row_number() over (
        partition by date, event, page_type, source_type, engagement_type, device, territory
        order by _ingested_at desc
    ) = 1
)

select * from deduped
