-- Staging: campaigns. Cast types, dedup to one row per campaign_id (latest ingest).
-- Raw stores all fields as STRING (load_json_rows_to_raw contract).
-- basic_details / segmentation_details are Python str(dict) -- accessed as opaque strings.
-- Nested field extraction deferred to mart layer if needed.

with source as (
    select * from {{ source('moengage_raw', 'raw_campaigns') }}
),

typed as (
    select
        campaign_id,
        channel,
        status,
        campaign_delivery_type,
        safe_cast(created_at as timestamp)      as created_at,
        safe_cast(sent_time as timestamp)        as sent_time,

        -- raw nested fields kept as strings for auditability
        basic_details,
        segmentation_details,
        conversion_goal_details,

        _ingested_at,
        _source,
        _run_id,
        safe_cast(_extract_from as date)        as _extract_from,
        safe_cast(_extract_to as date)          as _extract_to,
        _schema_flag
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
