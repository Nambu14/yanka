from pathlib import Path

from yanka.paths import (
    DATA_DIR_ENV_VAR,
    DEFAULT_DATA_DIR,
    ensure_data_layout,
    resolve_data_paths,
)


def test_default_data_dir(monkeypatch) -> None:
    monkeypatch.delenv(DATA_DIR_ENV_VAR, raising=False)
    paths = resolve_data_paths()
    expected_root = DEFAULT_DATA_DIR.expanduser().resolve()
    assert paths.data_dir == expected_root
    assert paths.records_dir == expected_root / "records"
    assert paths.changelog_path == expected_root / "changelog.jsonl"
    assert paths.graph_dir == expected_root / "graph"
    assert paths.vectors_dir == expected_root / "vectors"
    assert paths.config_path == expected_root / "config.yaml"


def test_env_override(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "from-env"
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(target))
    paths = resolve_data_paths()
    assert paths.data_dir == target.resolve()


def test_explicit_overrides_env(tmp_path: Path, monkeypatch) -> None:
    explicit = tmp_path / "explicit"
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(tmp_path / "from-env"))
    paths = resolve_data_paths(explicit)
    assert paths.data_dir == explicit.resolve()


def test_custom_data_dir(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    assert paths.data_dir == tmp_path.resolve()
    assert paths.records_dir == tmp_path / "records"
    assert paths.config_path == tmp_path / "config.yaml"


def test_ensure_data_layout_creates_dirs(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    assert not paths.records_dir.exists()

    result = ensure_data_layout(paths)

    assert result is paths
    assert paths.records_dir.is_dir()
    assert paths.graph_dir.is_dir()
    assert paths.vectors_dir.is_dir()
    assert not paths.config_path.exists()
    assert not paths.changelog_path.exists()


def test_ensure_data_layout_is_idempotent(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    ensure_data_layout(paths)
    ensure_data_layout(paths)
    assert paths.records_dir.is_dir()


def test_tilde_expansion(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    paths = resolve_data_paths("~/custom-yanka")
    assert paths.data_dir == (home / "custom-yanka").resolve()
