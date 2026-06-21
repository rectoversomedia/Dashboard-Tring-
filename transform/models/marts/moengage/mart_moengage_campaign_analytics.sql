-- Mart: campaign analytics (Group E). Grain: campaign x platform x date window.
-- Adds campaign metadata (name, tags) to the push stats.
-- Conversion empty unless a goal is configured per campaign (kept as null, not zero).
-- Full refresh each run; partitioned by _extract_from, clustered by platform x channel.

select
    s.campaign_id,
    c.channel,
    c.status                                                            as campaign_status,
    c.campaign_delivery_type,
    c.basic_details                                                     as campaign_basic_details,
    s.platform,
    s._extract_from                                                     as stats_date_from,
    s._extract_to                                                       as stats_date_to,

    sum(s.sent)                                                         as sent,
    sum(s.impression)                                                   as open_proxy,
    sum(s.click)                                                        as click,
    sum(s.attempted)                                                    as attempted,
    sum(s.failed)                                                       as failed,

    -- open rate proxy = impression / sent
    safe_divide(sum(s.impression), nullif(sum(s.sent), 0))             as open_proxy_rate,

    -- click rate = click / sent
    safe_divide(sum(s.click), nullif(sum(s.sent), 0))                  as click_rate,

    -- delivery rate = sent / attempted
    safe_divide(sum(s.sent), nullif(sum(s.attempted), 0))              as delivery_rate,

    -- conversion_goal_stats stored as string; non-empty means a goal was configured
    -- treat empty dict string as null (goal not configured)
    case
        when s.conversion_goal_stats = '{}' then null
        else s.conversion_goal_stats
    end                                                                 as conversion_goal_stats_raw

from {{ ref('stg_moengage_campaign_stats') }} s
left join {{ ref('stg_moengage_campaigns') }} c
    on s.campaign_id = c.campaign_id
where s.variation = 'all_variations'
group by 1, 2, 3, 4, 5, 6, 7, 8,
    case when s.conversion_goal_stats = '{}' then null else s.conversion_goal_stats end
