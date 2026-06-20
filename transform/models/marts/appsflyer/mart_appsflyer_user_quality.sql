-- Mart: user quality. Grain: date x media_source x campaign x platform x country.
-- Pivots event categories; joins cost from campaign_performance.
-- conversion_rate = registrations / installs, cost_per_registration = cost / registrations.

with events as (
    select
        event_date                          as date,
        media_source,
        campaign,
        country_code,
        _platform                           as platform,
        countif(event_category = 'open_app')        as open_app,
        countif(event_category = 'login')           as login,
        countif(event_category = 'purchase')        as purchase,
        countif(event_category = 'registrations')   as registrations
    from {{ ref('stg_appsflyer_in_app_events') }}
    group by 1, 2, 3, 4, 5
),

installs as (
    select
        install_date                        as date,
        media_source,
        campaign,
        country_code,
        _platform                           as platform,
        count(*)                            as installs
    from {{ ref('stg_appsflyer_installs') }}
    group by 1, 2, 3, 4, 5
),

costs as (
    select
        date,
        media_source,
        campaign,
        country_code,
        platform,
        sum(cost)                           as cost
    from {{ ref('mart_appsflyer_campaign_performance') }}
    group by 1, 2, 3, 4, 5
)

select
    coalesce(e.date, i.date)                    as date,
    coalesce(e.media_source, i.media_source)    as media_source,
    coalesce(e.campaign, i.campaign)            as campaign,
    coalesce(e.country_code, i.country_code)    as country_code,
    coalesce(e.platform, i.platform)            as platform,
    coalesce(e.open_app, 0)                     as open_app,
    coalesce(e.login, 0)                        as login,
    coalesce(e.purchase, 0)                     as purchase,
    coalesce(e.registrations, 0)                as registrations,
    coalesce(i.installs, 0)                     as installs,
    coalesce(c.cost, 0)                         as cost,

    -- conversion_rate = registrations / installs
    -- NOTE: can exceed 1.0 due to date grain mismatch — events use event_date, installs use
    -- install_date. A user installing on day T and registering on day T+3 causes the numerator
    -- and denominator to land on different dates in the same campaign grain.
    safe_divide(
        coalesce(e.registrations, 0),
        nullif(coalesce(i.installs, 0), 0)
    )                                           as conversion_rate,

    -- cost_per_registration = cost / registrations
    safe_divide(
        coalesce(c.cost, 0),
        nullif(coalesce(e.registrations, 0), 0)
    )                                           as cost_per_registration

from events e
full outer join installs i
    on e.date = i.date
    and e.media_source = i.media_source
    and e.campaign = i.campaign
    and e.country_code = i.country_code
    and e.platform = i.platform
left join costs c
    on coalesce(e.date, i.date) = c.date
    and coalesce(e.media_source, i.media_source) = c.media_source
    and coalesce(e.campaign, i.campaign) = c.campaign
    and coalesce(e.country_code, i.country_code) = c.country_code
    and coalesce(e.platform, i.platform) = c.platform