import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATA_DIR = Path("~/.yanka")
DATA_DIR_ENV_VAR = "YANKA_DATA_DIR"


@dataclass(frozen=True)
class DataPaths:
    data_dir: Path
    records_dir: Path
    changelog_path: Path
    graph_dir: Path
    vectors_dir: Path
    runtime_dir: Path
    config_path: Path
    pending_log_session_path: Path


_LAYOUT_DIRS = ("records_dir", "graph_dir", "vectors_dir", "runtime_dir")


def resolve_data_paths(data_dir: Path | str | None = None) -> DataPaths:
    """Resolve storage paths.

    Precedence: explicit arg > config.data_dir > YANKA_DATA_DIR > ~/.yanka.
    """
    if data_dir is not None:
        return _paths_for_root(_expand(data_dir))

    bootstrap = _expand(_bootstrap_data_dir_root())
    config_path = bootstrap / "config.yaml"
    if config_path.is_file():
        from yanka.config import load_config

        config = load_config(_paths_for_root(bootstrap))
        config_root = _expand(config.data_dir)
        if config_root != bootstrap:
            return resolve_data_paths(config_root)

    return _paths_for_root(bootstrap)


def ensure_data_layout(paths: DataPaths | None = None) -> DataPaths:
    """Create records/, graph/, and vectors/ under the data directory if missing."""
    resolved = paths if paths is not None else resolve_data_paths()
    for name in _LAYOUT_DIRS:
        getattr(resolved, name).mkdir(parents=True, exist_ok=True)
    return resolved


def _bootstrap_data_dir_root() -> Path | str:
    """Env > ~/.yanka — used only to locate config before full resolution."""
    env_value = os.environ.get(DATA_DIR_ENV_VAR)
    if env_value:
        return env_value
    return DEFAULT_DATA_DIR


def _paths_for_root(root: Path) -> DataPaths:
    return DataPaths(
        data_dir=root,
        records_dir=root / "records",
        changelog_path=root / "changelog.jsonl",
        graph_dir=root / "graph",
        vectors_dir=root / "vectors",
        runtime_dir=root / "runtime",
        config_path=root / "config.yaml",
        pending_log_session_path=root / "runtime" / "pending_log_session.json",
    )


def _expand(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()
