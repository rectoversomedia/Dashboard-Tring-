-- Mart: daily active devices (DAD). Grain: date x platform (android | ios).
-- DAD = COUNT(DISTINCT appsflyer_id) with an app-open event (SplashScreen_Loading) that day.
--
-- IMPORTANT: this is DEVICE-level, NOT user-level. It is Daily Active DEVICES, not DAU.
--   appsflyer_id identifies one install on one device, not a person:
--     - one person on 2 devices  = 2 (over-count)
--     - reinstall = new appsflyer_id = counted again (over-count)
--     - app opened without login   = still counted
--   Person-level DAU needs a login user_id (MoEngage, paid add-on) and is not built here.
--   Use this column as a DAU proxy only, and label it as devices in the dashboard.
--
-- Play Console DAU is not available at all (Google exposes no DAU via API/GCS); AppsFlyer
-- is the only automated, free active-count source, and it covers both android and ios.

select
    event_date                          as date,
    _platform                           as platform,
    count(distinct appsflyer_id)        as daily_active_devices
from {{ ref('stg_appsflyer_in_app_events') }}
where event_category = 'open_app'       -- SplashScreen_Loading
group by 1, 2
