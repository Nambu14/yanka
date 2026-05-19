"""First-run setup wizard."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import click

from whyline.config import WhylineConfig, default_config, save_config
from whyline.paths import (
    DEFAULT_DATA_DIR,
    DataPaths,
    _expand,
    ensure_data_layout,
    resolve_data_paths,
)
from whyline.secrets import set_api_key

PROVIDER_CHOICES: dict[str, str] = {
    "1": "claude",
    "2": "openai",
    "3": "google",
    "4": "ollama",
}

PromptFn = Callable[..., str]


def config_exists(paths: DataPaths) -> bool:
    return paths.config_path.is_file()


def run_first_run(
    *,
    bootstrap: DataPaths | None = None,
    prompt_fn: PromptFn | None = None,
    echo_fn: Callable[[str], None] | None = None,
) -> tuple[DataPaths, WhylineConfig]:
    """Interactive setup when config.yaml is missing."""
    prompt = prompt_fn or click.prompt
    echo = echo_fn or click.echo

    echo("")
    echo("  Welcome to Whyline.")
    echo("")

    suggested = bootstrap.data_dir if bootstrap else _expand(DEFAULT_DATA_DIR)
    default_dir = _display_path(suggested)
    data_dir_answer = prompt(
        "  Where should decisions be stored?",
        default=default_dir,
        show_default=True,
    )
    paths = resolve_data_paths(data_dir_answer or default_dir)
    ensure_data_layout(paths)

    echo("")
    echo("  Which LLM provider would you like to use?")
    echo("  [1] Claude (recommended)")
    echo("  [2] OpenAI")
    echo("  [3] Google")
    echo("  [4] Ollama (local)")
    echo("")
    choice = prompt(
        "  >",
        type=click.Choice(list(PROVIDER_CHOICES.keys())),
        show_choices=False,
    )
    provider = PROVIDER_CHOICES[choice]

    if provider != "ollama":
        api_key = prompt("  API key", hide_input=True)
        if api_key:
            set_api_key(provider, api_key)

    config = default_config(paths.data_dir)
    config.llm.provider = provider
    save_config(paths, config)

    storage = _display_path(paths.data_dir)
    echo("")
    echo(f"  ✓ Ready. Your decisions will be stored in {storage}/")
    echo("")
    echo("  Type /log to record something, /ask to query, /help for more.")
    echo("")
    return paths, config


def _display_path(path: Path) -> str:
    home = Path.home()
    try:
        relative = path.resolve().relative_to(home)
    except ValueError:
        return str(path)
    return f"~/{relative}" if relative.parts else str(path)
