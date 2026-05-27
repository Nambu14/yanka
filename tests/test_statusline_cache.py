from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from yanka.paths import ensure_data_layout, resolve_data_paths
from yanka.repl.format import format_statusline
from yanka.repl.statusline_cache import StatuslineCache


def test_statusline_cache_reuses_count_without_rescanning(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    cache = StatuslineCache(paths)
    calls = 0

    def counting_iter(_paths):
        nonlocal calls
        calls += 1
        return iter([])

    with patch("yanka.repl.statusline_cache.iter_records", counting_iter):
        assert cache.record_count() == 0
        assert cache.record_count() == 0

    assert calls == 1


def test_statusline_cache_invalidate_forces_rescan(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    cache = StatuslineCache(paths)
    calls = 0

    def counting_iter(_paths):
        nonlocal calls
        calls += 1
        return iter([])

    with patch("yanka.repl.statusline_cache.iter_records", counting_iter):
        cache.record_count()
        cache.invalidate()
        cache.record_count()

    assert calls == 2


def test_format_statusline_with_cache_matches_uncached(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    cache = StatuslineCache(paths)

    assert format_statusline(paths, cache=cache) == format_statusline(paths)
