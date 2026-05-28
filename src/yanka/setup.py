"""First-run setup wizard."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import click

from yanka.config import YankaConfig, default_config, default_llm_config, save_config
from yanka.paths import (
    DEFAULT_DATA_DIR,
    DataPaths,
    _expand,
    ensure_data_layout,
    resolve_data_paths,
)
from yanka.secrets import get_api_key, set_api_key

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
) -> tuple[DataPaths, YankaConfig]:
    """Interactive setup when config.yaml is missing."""
    prompt = prompt_fn or click.prompt
    echo = echo_fn or click.echo

    echo("")
    echo("  Welcome to yanka.")
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
        existing = get_api_key(provider)
        if existing:
            echo("  API key: (using keychain / environment)")
        else:
            api_key = prompt(
                "  API key (Enter to skip if set in keychain or env)",
                default="",
                hide_input=True,
                show_default=False,
            )
            if api_key:
                set_api_key(provider, api_key)
            elif not get_api_key(provider):
                echo(
                    "  No API key stored. Set OPENAI_API_KEY (etc.) or re-run "
                    'setup after: python3 -c "from yanka.secrets import set_api_key; '
                    f"set_api_key('{provider}', 'sk-...')\""
                )

    config = default_config(paths.data_dir)
    config.llm = default_llm_config(provider)
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
