"""Structured (key=value) logging shared by the pipeline and the CLI."""

from __future__ import annotations

import logging
import sys
from typing import Any

_CONFIGURED = False
_STANDARD_ATTRS = set(logging.LogRecord("x", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class KeyValueFormatter(logging.Formatter):
    """Renders ``msg`` plus any ``extra`` fields as ``key=value`` pairs."""

    def format(self, record: logging.LogRecord) -> str:
        stamp = self.formatTime(record, "%Y-%m-%dT%H:%M:%S")
        base = f"{stamp} {record.levelname:<7} {record.name} {record.getMessage()}"
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _STANDARD_ATTRS and not k.startswith("_")
        }
        if extras:
            base += " " + " ".join(f"{k}={_fmt(v)}" for k, v in extras.items())
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def _fmt(value: Any) -> str:
    text = str(value)
    if " " in text or "=" in text:
        return repr(text)
    return text


def configure_logging(level: str | int = "INFO") -> None:
    global _CONFIGURED
    root = logging.getLogger("electiondata")
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(KeyValueFormatter())
        root.addHandler(handler)
        root.propagate = False
        _CONFIGURED = True
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    if not _CONFIGURED:
        configure_logging()
    if name.startswith("electiondata"):
        return logging.getLogger(name)
    return logging.getLogger(f"electiondata.{name}")
