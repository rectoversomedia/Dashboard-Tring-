-- Staging: manual DAU export from Play Console UI (Statistics > Daily Active Users (DAU)).
-- Android only -- Play Console has no such metric for iOS. Loaded ad hoc, not on a schedule;
-- see the load SOP in docs/data-catalog-play-console.md.
-- Grain: one row per date x country (deduped by latest ingest).

{{
    config(
        materialized='table',
        partition_by={'field': 'date', 'data_type': 'date'},
        cluster_by=['country']
    )
}}

with source as (
    select * from {{ source('play_raw', 'raw_dau_manual') }}
),

deduped as (
    select *
    from source
    qualify row_number() over (
        partition by date, country
        order by _ingested_at desc
    ) = 1
)

select
    date,
    country,
    dau,
    notes,
    _ingested_at,
    _source
from deduped
