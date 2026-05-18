from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATA_DIR = Path("~/.whyline")


@dataclass(frozen=True)
class DataPaths:
    data_dir: Path
    records_dir: Path
    changelog_path: Path
    graph_dir: Path
    vectors_dir: Path
    config_path: Path


def resolve_data_paths(data_dir: Path | str | None = None) -> DataPaths:
    root = _expand(data_dir if data_dir is not None else DEFAULT_DATA_DIR)
    return _paths_for_root(root)


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
