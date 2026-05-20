from __future__ import annotations

from pathlib import Path

import pytest

from whyline.graph.store import GraphStoreError, clear_graph_db_cache, get_graph_db
from whyline.paths import ensure_data_layout, resolve_data_paths

ladybug = pytest.importorskip("ladybug")


@pytest.fixture(autouse=True)
def _clear_graph_cache() -> None:
    clear_graph_db_cache()
    yield
    clear_graph_db_cache()


def test_get_graph_db_creates_graph_dir(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    assert not paths.graph_dir.exists()

    get_graph_db(paths)

    assert paths.graph_dir.is_dir()


def test_get_graph_db_idempotent_same_connection(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))

    first = get_graph_db(paths)
    second = get_graph_db(paths)

    assert first is second
    assert first.connection is second.connection


def test_get_graph_db_different_paths_different_connections(
    tmp_path: Path,
) -> None:
    paths_a = ensure_data_layout(resolve_data_paths(tmp_path / "a"))
    paths_b = ensure_data_layout(resolve_data_paths(tmp_path / "b"))

    graph_a = get_graph_db(paths_a)
    graph_b = get_graph_db(paths_b)

    assert graph_a is not graph_b


def test_get_graph_db_connection_executes_cypher(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)

    graph.connection.execute(
        "CREATE NODE TABLE IF NOT EXISTS SpikeProbe(id STRING PRIMARY KEY)"
    )
    graph.connection.execute("CREATE (n:SpikeProbe {id: 'ok'})")
    result = graph.connection.execute(
        "MATCH (n:SpikeProbe {id: 'ok'}) RETURN n.id"
    )
    assert result.get_all() == [["ok"]]


def test_graph_store_error_when_ladybug_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    monkeypatch.delitem(sys.modules, "ladybug", raising=False)

    def fail_import(name: str, *args: object, **kwargs: object):
        if name == "ladybug":
            msg = "No module named 'ladybug'"
            raise ImportError(msg)
        return orig_import(name, *args, **kwargs)

    import builtins

    orig_import = builtins.__import__
    monkeypatch.setattr(builtins, "__import__", fail_import)
    clear_graph_db_cache()

    missing_root = Path("/tmp/whyline-test-graph-missing")
    paths = ensure_data_layout(resolve_data_paths(missing_root))
    with pytest.raises(GraphStoreError, match=r"\[graph\]") as exc:
        get_graph_db(paths)
    assert "ladybug is not installed" in str(exc.value)
