#!/usr/bin/env python3
"""Set the project version in pyproject.toml (single source of truth)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def set_version(root: Path, version: str) -> bool:
    """Update pyproject.toml. Returns True if the file changed."""
    pyproject = root / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    new_text, n = re.subn(r'^version = ".*"$', f'version = "{version}"', text, count=1, flags=re.M)
    if n != 1:
        raise SystemExit("could not update version in pyproject.toml")
    if new_text == text:
        return False
    pyproject.write_text(new_text, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help='Release version (e.g. "0.2.0")')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    changed = set_version(root, args.version)
    print("changed" if changed else "unchanged")


if __name__ == "__main__":
    main()
