# json logs so cloud logging parses severity + fields automatically
import json
import logging
import sys

# derived once from a blank record so it stays accurate across Python versions
_STDLIB_KEYS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


class _StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        # anything passed via extra={} ends up as a top-level field
        log_entry.update({k: v for k, v in record.__dict__.items() if k not in _STDLIB_KEYS})
        return json.dumps(log_entry, default=str)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
