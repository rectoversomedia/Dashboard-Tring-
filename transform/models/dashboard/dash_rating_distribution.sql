-- Dashboard: rating distribution (count + percentage) per star per platform.
-- Grain: one row per platform per star rating (5 rows per platform = 10 total).

with android as (
    select
        'android'   as platform,
        star_rating as rating,
        count(*)    as review_count
    from {{ ref('mart_play_console_reviews') }}
    group by star_rating
),

ios as (
    select
        'ios'                           as platform,
        safe_cast(rating as int64)      as rating,
        count(*)                        as review_count
    from {{ ref('mart_appstore_reviews') }}
    where safe_cast(rating as int64) is not null
    group by safe_cast(rating as int64)
),

combined as (
    select * from android
    union all
    select * from ios
),

with_total as (
    select
        platform,
        rating,
        review_count,
        sum(review_count) over (partition by platform) as total_reviews
    from combined
)

select
    platform,
    rating,
    review_count,
    total_reviews,
    safe_divide(review_count, nullif(total_reviews, 0)) as pct
from with_total
