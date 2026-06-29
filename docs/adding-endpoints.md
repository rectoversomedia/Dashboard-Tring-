# Adding an Endpoint to an Existing Source

This guide is for adding a **new endpoint to a source that already exists** (for
example, pulling one more AppsFlyer report, or one more Play Console metric set).

If you instead want to add a brand new source (a new vendor like App Store
Connect), see `docs/runbook.md` section 11 "Adding a new data source".

Each source defines its endpoints in
`ingestion/src/tring_ingest/sources/<source>/endpoints.py`. The three live
sources use three different shapes, so the steps differ per source. Pick the
one that matches the source you are extending.

---

## How each source declares endpoints

| Source | Shape in `endpoints.py` | How extract loops |
|---|---|---|
| AppsFlyer | a list `ENDPOINTS` of `Endpoint(name, bq_table, path_template, extra_params)` | iterates the list x apps |
| Play Console | a list `METRIC_SETS` of dicts (Reporting API) plus a fixed reviews URL | iterates the list |
| MoEngage | path constants (`SEARCH_PATH`, `STATS_PATH`) and dataclass payloads | hard-coded two-step flow |

AppsFlyer and Play Console are list-driven, so adding an endpoint is mostly
"append one entry". MoEngage is flow-driven, so adding an endpoint means writing
a new step in `extract.py`.

---

## A. AppsFlyer: add a report endpoint

File: `ingestion/src/tring_ingest/sources/appsflyer/endpoints.py`

1. Append a new `Endpoint(...)` to the `ENDPOINTS` list:

   ```python
   Endpoint(
       name="uninstalls",                 # short label used in logs
       bq_table="raw_uninstalls",         # raw table; auto-created on first load
       path_template="/api/raw-data/export/app/{app_id}/uninstall_events_report/v5",
       extra_params={},                   # any extra query params for this report
   ),
   ```

2. That is all the extract code needs. `extract.py` loops every entry in
   `ENDPOINTS` for every app, so the new report is pulled automatically. The raw
   BigQuery table is created by the loader on first run; you do not pre-create it.

3. Optional but usually wanted: add a staging model
   `transform/models/staging/appsflyer/stg_<name>.sql` and reference the new raw
   table, then a mart if the dashboard needs it. Add tests in the matching `.yml`.

4. Rebuild + redeploy the image (the new path string lives in the image):

   ```bash
   gcloud builds submit . --config=cloudbuild/build-push.yaml --substitutions="_PROJECT=$PROJECT"
   gcloud run jobs update extract-appsflyer --image=asia-southeast2-docker.pkg.dev/$PROJECT/tring-service/pipeline:latest --command=python --args="-m,tring_ingest,--source,appsflyer" --region=asia-southeast2 --project=$PROJECT
   ```

   On client prod this happens automatically: a push triggers Cloud Build, which
   rebuilds the shared image and rolls it onto all extract jobs.

---

## B. Play Console: add a Reporting API metric set

File: `ingestion/src/tring_ingest/sources/play_console/endpoints.py`

1. Append a dict to `METRIC_SETS`:

   ```python
   {
       "name": "slowRenderingRateMetricSet",   # exact metric set id from the API
       "table": "raw_slow_rendering_rate",      # raw table name
       "metrics": ["slowRenderingRate", "slowRenderingRate28dUserWeighted"],
       "dimensions": ["versionCode"],           # minimum required dimensions
   },
   ```

   Look up the exact metric set name, valid metrics, and required dimensions in
   the Play Developer Reporting API docs. Some metric sets require a specific
   dimension (for example `errorCountMetricSet` requires `reportType`) or the
   API returns a 400.

2. `extract.py` iterates `METRIC_SETS`, so the new set is queried and flattened
   automatically by `flatten_reporting_row`. No extract change needed unless the
   response has a new nested shape.

3. Add staging/mart models and tests as in section A step 3.

4. Rebuild + redeploy, but the job is `extract-play-console`:

   ```bash
   gcloud run jobs update extract-play-console --image=asia-southeast2-docker.pkg.dev/$PROJECT/tring-service/pipeline:latest --command=python --args="-m,tring_ingest,--source,play_console" --region=asia-southeast2 --project=$PROJECT
   ```

> Reviews (Publisher API) are a separate fixed call, not part of `METRIC_SETS`.
> Adding another Publisher API resource is closer to the MoEngage case below:
> add a URL helper and a flatten function, then call them from `extract.py`.

---

## C. MoEngage: add an endpoint

File: `ingestion/src/tring_ingest/sources/moengage/endpoints.py`

MoEngage is not list-driven. The extract is a fixed two-step flow (search
campaigns, then fetch stats). Adding an endpoint means adding a step.

1. Add a path constant and, if the endpoint takes a body, a payload builder:

   ```python
   EXPORT_PATH = "/core-services/v1/campaigns/export"

   def build_export_payload(request_id: str, campaign_ids: list[str]) -> dict:
       return {"request_id": request_id, "campaign_ids": campaign_ids}
   ```

   Mind the documented API limits (max 15 results per search page, max 10
   campaign IDs per stats request, max 30-day window). New endpoints may have
   their own limits, so verify live before assuming.

2. In `extract.py`, add the new step: call the client, flatten the response into
   a flat dict of strings, and load with `load_json_rows_to_raw(...)` into a new
   raw table. Follow the existing search/stats steps as the template. Keep the
   collect-errors-raise-once pattern so one failing step does not kill the rest.

3. Add staging/mart models and tests as in section A step 3.

4. Rebuild + redeploy `extract-moengage`:

   ```bash
   gcloud run jobs update extract-moengage --image=asia-southeast2-docker.pkg.dev/$PROJECT/tring-service/pipeline:latest --command=python --args="-m,tring_ingest,--source,moengage" --region=asia-southeast2 --project=$PROJECT
   ```

---

## After any endpoint change: verify

```bash
make lint
make test        # add or update tests for the new endpoint first

# run the one job for a single day and read the log line
gcloud run jobs execute extract-<source> --update-env-vars="DATE_FROM=2026-06-01,DATE_TO=2026-06-01" --region=asia-southeast2 --project=$PROJECT --wait
```

Then confirm the new raw table has rows in BigQuery, and run `dbt build` if you
added models. See `docs/testing.md` for the full check list.
