-- Staging: campaigns. Cast types, dedup to one row per campaign_id (latest ingest).
-- basic_details and segmentation_details stored as valid JSON (ingestion fix in bq_loader.py).
-- campaign_name and segment_tags extracted as scalar columns for mart joins.

with source as (
    select * from {{ source('moengage_raw', 'raw_campaigns') }}
),

typed as (
    select
        campaign_id,
        channel,
        status,
        campaign_delivery_type,
        safe_cast(created_at as timestamp)                              as created_at,
        safe_cast(sent_time as timestamp)                               as sent_time,

        -- extracted scalar fields
        json_value(basic_details, '$.name')                            as campaign_name,
        json_query(basic_details, '$.tags')                            as segment_tags,

        -- raw nested fields kept as JSON strings for auditability
        basic_details,
        segmentation_details,
        conversion_goal_details,

        _ingested_at,
        _source,
        _run_id,
        safe_cast(_extract_from as date)                               as _extract_from,
        safe_cast(_extract_to as date)                                 as _extract_to
    from source
),

deduped as (
    select *
    from typed
    qualify row_number() over (
        partition by campaign_id
        order by _ingested_at desc
    ) = 1
)

select * from deduped
