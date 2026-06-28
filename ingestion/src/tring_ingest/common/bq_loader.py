# lands appsflyer csv into bq raw: every source column as STRING, plus our metadata.
# string-everything means no value is ever lost or rejected at the boundary; typing
# happens later in dbt staging.
import contextlib
import csv
import io
import json
import uuid
from datetime import UTC, datetime

from google.api_core.exceptions import Conflict, NotFound
from google.cloud import bigquery

from tring_ingest.common.config import GCP_PROJECT, REGION
from tring_ingest.common.logging import get_logger

logger = get_logger(__name__)

METADATA_COLUMNS = [
    "_ingested_at",
    "_source",
    "_app_id",
    "_platform",
    "_run_id",
    "_extract_from",
    "_extract_to",
]


def _get_existing_columns(client: bigquery.Client, table_ref: str) -> set[str] | None:
    # returns set of column names already in the BQ table, or None if table doesn't exist yet
    try:
        table = client.get_table(table_ref)
        return {f.name for f in table.schema}
    except NotFound:
        return None


def _build_schema(source_columns: list[str]) -> list[bigquery.SchemaField]:
    fields = [bigquery.SchemaField(col, "STRING") for col in source_columns]
    fields += [
        bigquery.SchemaField("_ingested_at", "TIMESTAMP"),
        bigquery.SchemaField("_source", "STRING"),
        bigquery.SchemaField("_app_id", "STRING"),
        bigquery.SchemaField("_platform", "STRING"),
        bigquery.SchemaField("_run_id", "STRING"),
        bigquery.SchemaField("_extract_from", "DATE"),
        bigquery.SchemaField("_extract_to", "DATE"),
    ]
    return fields


def load_csv_to_raw(
    csv_content: str,
    dataset_id: str,
    table_id: str,
    source: str,
    app_id: str,
    platform: str,
    date_from: str,
    date_to: str,
    project_id: str = GCP_PROJECT,
) -> int:
    # append-only. staging dedupes by latest _ingested_at per natural key, so re-runs
    # and backfills are safe. returns the row count loaded.
    client = bigquery.Client(project=project_id)
    run_id = str(uuid.uuid4())
    ingested_at = datetime.now(UTC).isoformat()

    # first run in a fresh project won't have the dataset yet
    dataset_ref = bigquery.Dataset(f"{project_id}.{dataset_id}")
    dataset_ref.location = REGION
    with contextlib.suppress(Conflict):
        client.create_dataset(dataset_ref, exists_ok=True)

    # appsflyer prepends a UTF-8 BOM to its csv; left in, it corrupts the first column name
    csv_content = csv_content.lstrip("﻿")

    reader = csv.DictReader(io.StringIO(csv_content))
    all_source_columns = reader.fieldnames or []

    table_ref = f"{project_id}.{dataset_id}.{table_id}"
    existing = _get_existing_columns(client, table_ref)
    if existing is not None:
        source_columns = [c for c in all_source_columns if c in existing]
        dropped = set(all_source_columns) - set(source_columns)
        if dropped:
            logger.warning(f"dropping unknown columns not in BQ schema: {dropped}")
    else:
        source_columns = all_source_columns

    rows = []
    for row in reader:
        r = {col: row[col] for col in source_columns}
        r["_ingested_at"] = ingested_at
        r["_source"] = source
        r["_app_id"] = app_id
        r["_platform"] = platform
        r["_run_id"] = run_id
        r["_extract_from"] = date_from
        r["_extract_to"] = date_to
        rows.append(r)

    if not rows:
        logger.warning(
            "empty response, skipping load",
            extra={"table": table_id, "app_id": app_id, "platform": platform},
        )
        return 0

    schema = _build_schema(source_columns)

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        time_partitioning=bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="_ingested_at",
        ),
    )

    # load in chunks so the bq api call never holds the full rows list in memory at once.
    # in_app_events can be 500k+ rows; one big load_table_from_json call peaks at ~2x the
    # list size. 5k chunks keep each call small while reusing the same job_config.
    CHUNK_SIZE = 5_000
    for i in range(0, len(rows), CHUNK_SIZE):
        client.load_table_from_json(
            rows[i : i + CHUNK_SIZE], table_ref, job_config=job_config
        ).result()

    logger.info(
        f"loaded {len(rows)} rows to {table_id}",
        extra={"table": table_ref, "rows": len(rows)},
    )
    return len(rows)


def load_json_rows_to_raw(
    rows: list[dict],
    dataset_id: str,
    table_id: str,
    source: str,
    date_from: str,
    date_to: str,
    project_id: str = GCP_PROJECT,
) -> int:
    # JSON-based loader for sources that return JSON (not CSV). Same append-only contract
    # as load_csv_to_raw: all source fields as STRING, plus the standard metadata columns.
    if not rows:
        logger.warning("empty rows, skipping load", extra={"table": table_id})
        return 0

    client = bigquery.Client(project=project_id)
    run_id = str(uuid.uuid4())
    ingested_at = datetime.now(UTC).isoformat()

    dataset_ref = bigquery.Dataset(f"{project_id}.{dataset_id}")
    dataset_ref.location = REGION
    with contextlib.suppress(Conflict):
        client.create_dataset(dataset_ref, exists_ok=True)

    all_source_columns = sorted({k for row in rows for k in row})
    table_ref = f"{project_id}.{dataset_id}.{table_id}"
    existing = _get_existing_columns(client, table_ref)
    if existing is not None:
        source_columns = [c for c in all_source_columns if c in existing]
        dropped = set(all_source_columns) - set(source_columns)
        if dropped:
            logger.warning(f"dropping unknown columns not in BQ schema: {dropped}")
    else:
        source_columns = all_source_columns

    enriched = []
    for row in rows:
        r = {
            col: (json.dumps(v) if isinstance(v := row.get(col, ""), dict | list) else str(v))
            for col in source_columns
        }
        r["_ingested_at"] = ingested_at
        r["_source"] = source
        r["_app_id"] = ""
        r["_platform"] = ""
        r["_run_id"] = run_id
        r["_extract_from"] = date_from
        r["_extract_to"] = date_to
        enriched.append(r)

    schema = _build_schema(source_columns)

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        time_partitioning=bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="_ingested_at",
        ),
    )

    CHUNK_SIZE = 5_000
    for i in range(0, len(enriched), CHUNK_SIZE):
        client.load_table_from_json(
            enriched[i : i + CHUNK_SIZE], table_ref, job_config=job_config
        ).result()

    logger.info(
        f"loaded {len(enriched)} rows to {table_id}",
        extra={"table": table_ref, "rows": len(enriched)},
    )
    return len(enriched)
