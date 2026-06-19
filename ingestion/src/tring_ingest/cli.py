"""Entrypoint: python -m tring_ingest --source appsflyer --from YYYY-MM-DD --to YYYY-MM-DD"""

import argparse
import sys

from tring_ingest.common.logging import get_logger

logger = get_logger(__name__)

SOURCES = ["appsflyer", "moengage", "play_console", "app_store"]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Dashboard Monitoring & AI Insight — data pipeline ingestion")
    parser.add_argument("--source", required=True, choices=SOURCES, help="Data source to extract")
    parser.add_argument("--from", dest="date_from", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", required=True, help="End date YYYY-MM-DD")
    return parser.parse_args(argv)


def main(argv=None):
    import os
    if not os.environ.get("GCP_PROJECT"):
        raise SystemExit("ERROR: GCP_PROJECT environment variable is required. Set it before running.")

    args = parse_args(argv)
    logger.info(
        "Starting extraction",
        extra={"source": args.source, "from": args.date_from, "to": args.date_to},
    )

    if args.source == "appsflyer":
        from tring_ingest.sources.appsflyer.extract import run

        run(date_from=args.date_from, date_to=args.date_to)
    elif args.source == "moengage":
        raise NotImplementedError("MoEngage source not yet implemented")
    elif args.source == "play_console":
        raise NotImplementedError("Play Console source not yet implemented")
    elif args.source == "app_store":
        raise NotImplementedError("App Store source not yet implemented")
    else:
        logger.error("Unknown source", extra={"source": args.source})
        sys.exit(1)

    logger.info("Extraction complete", extra={"source": args.source})


if __name__ == "__main__":
    main()
