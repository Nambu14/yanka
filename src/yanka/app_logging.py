"""Application logging to runtime/yanka.log."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from yanka.paths import DataPaths

LOGGER_NAME = "yanka"
LOG_FILENAME = "yanka.log"
MAX_LOG_BYTES = 5_000_000
BACKUP_COUNT = 3


def configure_app_logging(paths: DataPaths) -> Path:
    """Configure bounded rotating file logging under ``paths.runtime_dir``."""
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    log_path = paths.runtime_dir / LOG_FILENAME
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler) and _handler_points_to(handler, log_path):
            return log_path

    handler = RotatingFileHandler(
        log_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return log_path


def get_logger(name: str | None = None) -> logging.Logger:
    """Return root yanka logger or a child logger."""
    if not name:
        return logging.getLogger(LOGGER_NAME)
    child = name.rsplit(".", maxsplit=1)[-1]
    return logging.getLogger(f"{LOGGER_NAME}.{child}")


def log_exception(
    logger: logging.Logger,
    message: str,
    exc: BaseException,
    **context: Any,
) -> None:
    """Log an exception with traceback and structured context."""
    if context:
        context_text = " ".join(f"{key}={value!r}" for key, value in sorted(context.items()))
        logger.error("%s | %s", message, context_text, exc_info=exc)
        return
    logger.error("%s", message, exc_info=exc)


def _handler_points_to(handler: RotatingFileHandler, log_path: Path) -> bool:
    try:
        return Path(handler.baseFilename).resolve() == log_path.resolve()
    except OSError:
        return False
