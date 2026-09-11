-- Dashboard: rating distribution per day per platform.
-- Grain: one row per date x platform x star rating.
--
-- Replaces dash_rating_distribution, which has two defects:
--   1. No date column, so Looker's date range control is silently ignored.
--   2. Android reads the API-backed mart, which never receives rating-only reviews
--      (~55% of ratings, mostly 5-star) and so understates avg rating by ~1 star.
--
-- Android here comes from the GCS review export instead, which carries both
-- rating-only reviews and the true submit date.
--
-- Percentage is deliberately NOT precomputed: a window function over the whole
-- table would be wrong the moment a viewer filters by date. Compute it in Looker
-- as review_count / SUM(review_count).

with android as (
    select
        review_date     as date,
        'android'       as platform,
        star_rating     as rating,
        count(*)        as review_count,
        countif(has_review_text)        as with_text_count,
        countif(not has_review_text)    as rating_only_count
    from {{ ref('mart_play_console_gcs_reviews') }}
    where star_rating is not null
    group by review_date, star_rating
),

ios as (
    select
        review_date                     as date,
        'ios'                           as platform,
        safe_cast(rating as int64)      as rating,
        count(*)                        as review_count,
        -- App Store reviews always carry a body; no rating-only split available
        count(*)                        as with_text_count,
        0                               as rating_only_count
    from {{ ref('mart_appstore_reviews') }}
    where safe_cast(rating as int64) is not null
    group by review_date, safe_cast(rating as int64)
)

select * from android
union all
select * from ios
