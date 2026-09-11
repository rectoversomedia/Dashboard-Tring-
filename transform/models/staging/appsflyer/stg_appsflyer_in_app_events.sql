-- Staging: in-app events. Cast types, map event_name to category via seed, dedup re-extracts.
-- Dedup strategy: keep the row with the latest _ingested_at per natural event key.
-- Raw is append-only (WRITE_APPEND) and overlapping extract windows re-fetch events that are
-- already loaded, so one event can land many times  -  observed up to 4x in BQ. Without this,
-- every countif() downstream (open_app, login, purchase, registrations) is inflated.
-- Deduped on the raw columns rather than after typing because `Event Value` separates two
-- genuine same-second events of the same name and is not carried into the typed output.

with source as (
    select * from {{ source('appsflyer_raw', 'raw_in_app_events') }}
    qualify row_number() over (
        partition by `Appsflyer ID`, `Event Name`, `Event Time`, `Event Value`, _platform
        order by _ingested_at desc
    ) = 1
),

mapping as (
    select * from {{ ref('appsflyer_event_mapping') }}
),

typed as (
    select
        `Appsflyer ID`                              as appsflyer_id,
        `Event Name`                                as event_name,
        safe_cast(`Event Time` as timestamp)        as event_time,
        date(safe_cast(`Event Time` as timestamp))  as event_date,
        `Media Source`                              as media_source,
        `Campaign`                                  as campaign,
        `Campaign ID`                               as campaign_id,
        `Country Code`                              as country_code,
        `Platform`                                  as platform,
        _platform,
        _app_id,
        _ingested_at,
        _run_id,
        _extract_from,
        _extract_to
    from source
)

select
    t.*,
    m.category as event_category
from typed t
left join mapping m on t.event_name = m.event_name
