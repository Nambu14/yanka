from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _read_version() -> str:
    try:
        return version("yanka")
    except PackageNotFoundError:
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            if line.startswith('version = "'):
                return line.split('"', 2)[1]
        raise RuntimeError("version not found in pyproject.toml") from None


__version__ = _read_version()
