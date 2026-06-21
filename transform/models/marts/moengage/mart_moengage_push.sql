-- Mart: push notification metrics (Group A). Grain: campaign x platform x date window.
-- impression used as open proxy (push has no native open event).
-- Full refresh each run; partitioned by _extract_from, clustered by platform x channel.

select
    s.campaign_id,
    c.channel,
    c.status                                                            as campaign_status,
    c.campaign_delivery_type,
    s.platform,
    s._extract_from                                                     as stats_date_from,
    s._extract_to                                                       as stats_date_to,

    sum(s.sent)                                                         as sent,
    -- impression = open proxy for push (no native open event)
    sum(s.impression)                                                   as open_proxy,
    sum(s.click)                                                        as click,

    -- CTR from API (ratio of click to sent/attempted)
    safe_divide(sum(s.click), nullif(sum(s.sent), 0))                  as click_rate,

    -- impression rate = impression / sent
    safe_divide(sum(s.impression), nullif(sum(s.sent), 0))             as open_proxy_rate

from {{ ref('stg_moengage_campaign_stats') }} s
left join {{ ref('stg_moengage_campaigns') }} c
    on s.campaign_id = c.campaign_id
-- keep only the all_variations aggregate to avoid double-counting per-variation splits
where s.variation = 'all_variations'
group by 1, 2, 3, 4, 5, 6, 7
