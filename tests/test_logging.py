from __future__ import annotations

from pathlib import Path

from yanka.app_logging import (
    BACKUP_COUNT,
    LOG_FILENAME,
    MAX_LOG_BYTES,
    configure_app_logging,
    get_logger,
    log_exception,
)
from yanka.paths import ensure_data_layout, resolve_data_paths


def _reset_app_logger() -> None:
    logger = get_logger()
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_configure_app_logging_creates_runtime_log_file(tmp_path: Path) -> None:
    _reset_app_logger()
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    log_path = configure_app_logging(paths)
    logger = get_logger("test")
    logger.info("hello logging")

    assert log_path == paths.runtime_dir / LOG_FILENAME
    assert log_path.is_file()
    assert "hello logging" in log_path.read_text(encoding="utf-8")


def test_configure_app_logging_is_idempotent(tmp_path: Path) -> None:
    _reset_app_logger()
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    first = configure_app_logging(paths)
    second = configure_app_logging(paths)
    logger = get_logger()

    assert first == second
    assert (
        sum(
            1
            for handler in logger.handlers
            if getattr(handler, "baseFilename", None) is not None
            and Path(handler.baseFilename) == first
        )
        == 1
    )


def test_log_exception_writes_traceback_and_context(tmp_path: Path) -> None:
    _reset_app_logger()
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    log_path = configure_app_logging(paths)
    logger = get_logger("test")

    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        log_exception(logger, "failure during test", exc, command="ask")

    text = log_path.read_text(encoding="utf-8")
    assert "failure during test" in text
    assert "command='ask'" in text
    assert "RuntimeError: boom" in text


def test_logging_rotation_constants_are_bounded() -> None:
    assert MAX_LOG_BYTES == 5_000_000
    assert BACKUP_COUNT == 3
