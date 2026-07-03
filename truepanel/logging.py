"""
TruePanel logging helpers
"""

import logging
from pathlib import Path


DEFAULT_LOG_FILE = "/var/log/truepanel.log"


def setup_logging(level="INFO", log_file=DEFAULT_LOG_FILE):
    logger = logging.getLogger("truepanel")
    logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    try:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        logger.debug("File logging unavailable", exc_info=True)

    return logger
