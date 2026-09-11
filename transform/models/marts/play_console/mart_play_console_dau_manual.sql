-- Mart: manual DAU (real, user-level -- not a device proxy) from Play Console UI export.
-- Android only -- Play Console exposes no such metric for iOS.
-- Ad hoc loaded, not on the extract schedule; see the load SOP in data-catalog-play-console.md.
-- country = 'all' is Google's own global figure, not a sum of the other rows (it may include
-- countries not broken out separately). Grain: one row per date x country.

select
    date,
    'android'         as platform,
    country,
    dau               as daily_active_users,
    notes
from {{ ref('stg_play_console_dau_manual') }}
