-- Dashboard: average rating per day, both platforms in one table.
-- Grain: one row per platform per date.
-- Android rating = INT64 (star_rating). iOS rating = STRING cast to INT64.

with android as (
    select
        review_date     as date,
        'android'       as platform,
        count(*)        as review_count,
        avg(cast(star_rating as float64))   as avg_rating,
        countif(star_rating = 1)            as rating_1,
        countif(star_rating = 2)            as rating_2,
        countif(star_rating = 3)            as rating_3,
        countif(star_rating = 4)            as rating_4,
        countif(star_rating = 5)            as rating_5
    from {{ ref('mart_play_console_reviews') }}
    group by review_date
),

ios as (
    select
        review_date     as date,
        'ios'           as platform,
        count(*)        as review_count,
        avg(safe_cast(rating as float64))   as avg_rating,
        countif(safe_cast(rating as int64) = 1) as rating_1,
        countif(safe_cast(rating as int64) = 2) as rating_2,
        countif(safe_cast(rating as int64) = 3) as rating_3,
        countif(safe_cast(rating as int64) = 4) as rating_4,
        countif(safe_cast(rating as int64) = 5) as rating_5
    from {{ ref('mart_appstore_reviews') }}
    group by review_date
)

select * from android
union all
select * from ios
