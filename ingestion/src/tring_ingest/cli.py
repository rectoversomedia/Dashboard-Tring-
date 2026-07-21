# entrypoint: python -m tring_ingest --source appsflyer --from YYYY-MM-DD --to YYYY-MM-DD
# dates can also come from DATE_FROM/DATE_TO env vars (how cloud run jobs pass them);
# command-line args win over env vars.
import argparse
import os

from tring_ingest.common.logging import get_logger

logger = get_logger(__name__)

SOURCES = ["appsflyer", "moengage", "play_console", "app_store"]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="data pipeline ingestion")
    parser.add_argument("--source", required=True, choices=SOURCES)
    parser.add_argument("--from", dest="date_from", default=os.environ.get("DATE_FROM"))
    parser.add_argument("--to", dest="date_to", default=os.environ.get("DATE_TO"))
    parser.add_argument(
        "--snapshot", action="store_true", help="run one-time snapshot backfill (app_store only)"
    )
    parser.add_argument(
        "--gcs-stats",
        action="store_true",
        dest="gcs_stats",
        help="ingest Play Console GCS stats (installs/crashes/store_performance)",
    )
    args = parser.parse_args(argv)
    if not args.snapshot and (not args.date_from or not args.date_to):
        parser.error("--from/--to required (or set DATE_FROM/DATE_TO env vars)")
    return args


def main(argv=None):
    if not os.environ.get("GCP_PROJECT"):
        raise SystemExit("GCP_PROJECT env var is required")

    args = parse_args(argv)

    if args.snapshot:
        if args.source != "app_store":
            raise SystemExit("--snapshot only supported for --source app_store")
        logger.info("running app_store ONE_TIME_SNAPSHOT backfill")
        from tring_ingest.sources.app_store.extract import run_snapshot

        run_snapshot()
        return

    logger.info(f"extracting {args.source} {args.date_from}..{args.date_to}")

    if args.source == "appsflyer":
        from tring_ingest.sources.appsflyer.extract import run

        run(date_from=args.date_from, date_to=args.date_to)
    elif args.source == "moengage":
        from tring_ingest.sources.moengage.extract import run

        run(date_from=args.date_from, date_to=args.date_to)
    elif args.source == "play_console":
        if args.gcs_stats:
            from tring_ingest.sources.play_console.gcs_stats import run_gcs_stats

            run_gcs_stats(date_from=args.date_from, date_to=args.date_to)
        else:
            from tring_ingest.sources.play_console.extract import run

            run(date_from=args.date_from, date_to=args.date_to)
    elif args.source == "app_store":
        from tring_ingest.sources.app_store.extract import run

        run(date_from=args.date_from, date_to=args.date_to)
    else:
        raise NotImplementedError(f"{args.source} source not yet implemented")
