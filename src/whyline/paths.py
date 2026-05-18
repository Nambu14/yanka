import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATA_DIR = Path("~/.whyline")
DATA_DIR_ENV_VAR = "WHYLINE_DATA_DIR"


@dataclass(frozen=True)
class DataPaths:
    data_dir: Path
    records_dir: Path
    changelog_path: Path
    graph_dir: Path
    vectors_dir: Path
    config_path: Path


_LAYOUT_DIRS = ("records_dir", "graph_dir", "vectors_dir")


def resolve_data_paths(data_dir: Path | str | None = None) -> DataPaths:
    """Resolve storage paths.

    Precedence: explicit arg > WHYLINE_DATA_DIR > ~/.whyline.
    """
    root = _expand(_resolve_data_dir_root(data_dir))
    return _paths_for_root(root)


def ensure_data_layout(paths: DataPaths | None = None) -> DataPaths:
    """Create records/, graph/, and vectors/ under the data directory if missing."""
    resolved = paths if paths is not None else resolve_data_paths()
    for name in _LAYOUT_DIRS:
        getattr(resolved, name).mkdir(parents=True, exist_ok=True)
    return resolved


def _resolve_data_dir_root(explicit: Path | str | None) -> Path | str:
    if explicit is not None:
        return explicit
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
        config_path=root / "config.yaml",
    )


def _expand(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()
