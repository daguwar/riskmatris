"""Shared logging formatters for the application and uvicorn.

``build_log_formatter()`` is referenced from ``log_config.json`` (used via
``uvicorn --log-config``) so that uvicorn's own loggers (access/error) use
the same timestamped format as the application loggers – and switch to JSON
together with the app when RISKMATRIS_LOG_FORMAT=json.
"""

import json
import logging
import os

TEXT_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
TEXT_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


class JsonFormatter(logging.Formatter):
    """Structured JSON-lines logging (one JSON object per line) for production.

    Enabled with RISKMATRIS_LOG_FORMAT=json (set by default in the Docker
    image); the default "text" keeps the human-readable format for local dev.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def build_log_formatter() -> logging.Formatter:
    """Returns the JSON formatter or the timestamped text formatter.

    The choice follows RISKMATRIS_LOG_FORMAT so uvicorn's access log and the
    application log always end up in the same format.
    """
    if os.environ.get("RISKMATRIS_LOG_FORMAT", "text").strip().lower() == "json":
        return JsonFormatter()
    return logging.Formatter(TEXT_LOG_FORMAT, TEXT_LOG_DATEFMT)
