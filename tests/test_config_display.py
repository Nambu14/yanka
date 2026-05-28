from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from yanka.config import default_config, format_config_display, save_config
from yanka.paths import ensure_data_layout, resolve_data_paths


def test_format_config_display_shows_key_status_not_secret(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    config = default_config(paths.data_dir)
    config.llm.provider = "openai"
    save_config(paths, config)

    with patch(
        "yanka.secrets.get_api_key",
        side_effect=lambda p: "sk-secret" if p == "openai" else None,
    ):
        text = format_config_display(paths)

    assert f"Config file: {paths.config_path}" in text
    assert "api_key (openai): set" in text
    assert "api_key (claude): not set" in text
    assert "sk-secret" not in text
    assert "provider: openai" in text
