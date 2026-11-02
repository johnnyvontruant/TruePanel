"""Persistent, best-effort human-readable TruePanel flight log.

No logging failure is allowed to interrupt an alert or hardware operation.
The recorder records state transitions; callers decide when events are new.
"""
from datetime import datetime, timezone
from logging import Formatter, INFO, Logger, getLogger
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock

DEFAULT_PATH = "/var/lib/truepanel/logs/flight.log"
_lock = Lock()
_recorders = {}


def _recorder(path):
    path = str(Path(path))
    with _lock:
        if path in _recorders:
            return _recorders[path]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        logger = Logger("truepanel.flight." + str(len(_recorders)), level=INFO)
        logger.propagate = False
        handler = RotatingFileHandler(
            path, maxBytes=5 * 1024 * 1024, backupCount=7,
            encoding="utf-8",
        )
        handler.setFormatter(Formatter("%(message)s"))
        logger.addHandler(handler)
        _recorders[path] = logger
        return logger


def record(category, severity, message, *, path=DEFAULT_PATH):
    """Append one sanitized UTC event; return False on any I/O failure."""
    try:
        category = str(category).upper().replace("\n", " ").replace("|", "/")
        severity = str(severity).upper().replace("\n", " ").replace("|", "/")
        message = str(message).replace("\r", " ").replace("\n", " ")
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _recorder(path).info(
            "%s | %-8s | %-8s | %s", stamp, severity, category, message
        )
        return True
    except Exception:
        # Flight recording must never prevent alerts or hardware control.
        return False
