# lands appsflyer csv into bq raw: every source column as STRING, plus our metadata.
# string-everything means no value is ever lost or rejected at the boundary; typing
# happens later in dbt staging.
import contextlib
import csv
import io
import uuid
from datetime import UTC, datetime

from google.api_core.exceptions import Conflict
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
    "_schema_flag",
]


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
        bigquery.SchemaField("_schema_flag", "STRING"),
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
    expected_columns: list[str] | None = None,
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
    source_columns = reader.fieldnames or []

    schema_flag = ""
    if expected_columns:
        missing = set(expected_columns) - set(source_columns)
        extra = set(source_columns) - set(expected_columns)
        if missing or extra:
            schema_flag = f"missing={sorted(missing)};extra={sorted(extra)}"
            logger.warning(
                "Schema drift detected",
                extra={"table": table_id, "schema_flag": schema_flag},
            )

    rows = []
    for row in reader:
        row["_ingested_at"] = ingested_at
        row["_source"] = source
        row["_app_id"] = app_id
        row["_platform"] = platform
        row["_run_id"] = run_id
        row["_extract_from"] = date_from
        row["_extract_to"] = date_to
        row["_schema_flag"] = schema_flag
        rows.append(row)

    if not rows:
        logger.warning(
            "Empty response, skipping load",
            extra={"table": table_id, "app_id": app_id, "platform": platform},
        )
        return 0

    table_ref = f"{project_id}.{dataset_id}.{table_id}"
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

    load_job = client.load_table_from_json(rows, table_ref, job_config=job_config)
    load_job.result()

    logger.info(
        f"loaded {len(rows)} rows to {table_id}",
        extra={"table": table_ref, "rows": len(rows), "schema_flag": schema_flag or "ok"},
    )
    return len(rows)
