from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from whyline.ingest.extraction import RecordExtractionError
from whyline.paths import ensure_data_layout, resolve_data_paths
from whyline.records.io import read_record, write_record
from whyline.repl import (
    HELP_TEXT,
    format_history,
    format_status,
    run_log_command,
    run_repl,
)

FIXTURE = Path(__file__).parent / "fixtures" / "records" / "valid-decision.md"


def _run_with_inputs(inputs: list[str]) -> list[str]:
    values = iter(inputs)
    output: list[str] = []

    def input_fn(_prompt: str) -> str:
        return next(values)

    run_repl(
        resolve_data_paths(Path("/tmp/whyline-repl-test")),
        input_fn=input_fn,
        output_fn=output.append,
    )
    return output


def _run_with_paths(paths, inputs: list[str]) -> list[str]:
    values = iter(inputs)
    output: list[str] = []

    def input_fn(_prompt: str) -> str:
        return next(values)

    run_repl(paths, input_fn=input_fn, output_fn=output.append)
    return output


def _seed_record(paths, filename: str = "valid-decision.md") -> None:
    record = read_record(FIXTURE).record
    write_record(paths, record, filename=filename)


def test_repl_help_then_exit() -> None:
    output = _run_with_inputs(["/help", "/exit"])

    assert "Welcome to Whyline." in output
    assert HELP_TEXT in output
    assert "/ask      Query existing knowledge" in HELP_TEXT


def test_repl_quit_exits_cleanly() -> None:
    output = _run_with_inputs(["/quit"])

    assert "Welcome to Whyline." in output
    assert all("Unknown command" not in line for line in output)


def test_repl_ignores_empty_input() -> None:
    output = _run_with_inputs(["", "   ", "/exit"])

    assert "Welcome to Whyline." in output
    assert all("Unknown command" not in line for line in output)


def test_repl_unknown_slash_command() -> None:
    output = _run_with_inputs(["/bogus", "/exit"])

    assert "Unknown command: /bogus. Type /help for commands." in output


def test_repl_non_slash_input_guides_user() -> None:
    output = _run_with_inputs(["hello", "/exit"])

    assert "Commands start with /. Type /help for commands." in output


def test_repl_eof_exits_cleanly() -> None:
    output: list[str] = []

    def eof_input(_prompt: str) -> str:
        raise EOFError

    run_repl(
        resolve_data_paths(Path("/tmp/whyline-repl-eof-test")),
        input_fn=eof_input,
        output_fn=output.append,
    )

    assert "Welcome to Whyline." in output


def test_format_status_empty_kb(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))

    output = format_status(paths)

    assert f"Data dir: {paths.data_dir}" in output
    assert "Records: 0" in output


def test_repl_status_with_seeded_data(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_record(paths)

    output = _run_with_paths(paths, ["/status", "/exit"])
    status = "\n".join(output)

    assert "Records: 1" in status
    assert "Projects: main-platform" in status
    assert "Latest record: 2026-05-14" in status


def test_format_history_empty_kb(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))

    assert format_history(paths) == "No records yet."


def test_repl_history_with_seeded_data(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_record(paths)

    output = _run_with_paths(paths, ["/history", "/exit"])
    history = "\n".join(output)

    assert "2026-05-14" in history
    assert "active" in history
    assert "valid-decision.md" in history
    assert "Drop Redis for session storage" in history


def test_repl_rebuild_with_seeded_data(tmp_path: Path) -> None:
    from whyline.config import EmbeddingConfig, default_config, save_config
    from whyline.embeddings import EMBEDDING_DIM, register_embedding_backend

    def fake_embed(texts: list[str], _config: EmbeddingConfig) -> list[list[float]]:
        return [[1.0] + [0.0] * (EMBEDDING_DIM - 1) for _ in texts]

    register_embedding_backend("test", fake_embed)
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    config = default_config(paths.data_dir)
    config.embedding = EmbeddingConfig(provider="test", model="fake")
    save_config(paths, config)
    _seed_record(paths)

    output = _run_with_paths(paths, ["/rebuild", "/exit"])

    assert "Rebuilt indexes from 1 record(s)." in output


def test_log_command_empty_input_does_not_call_ingest(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    output: list[str] = []

    def fail_runner(*_args, **_kwargs):
        raise AssertionError("ingest runner should not be called")

    result = run_log_command(
        paths,
        input_fn=lambda _prompt: "   ",
        output_fn=output.append,
        ingest_runner=fail_runner,
    )

    assert result is None
    assert "Paste your decision note:" in output
    assert "Nothing to log." in output


def test_log_command_calls_ingest_runner_and_reports_saved_path(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    output: list[str] = []
    calls = []
    saved_path = paths.records_dir / "logged.md"

    def fake_runner(raw_dump, runner_paths, **kwargs):
        calls.append((raw_dump, runner_paths, kwargs))
        return SimpleNamespace(write_result=SimpleNamespace(path=saved_path))

    result = run_log_command(
        paths,
        input_fn=lambda _prompt: "We chose PostgreSQL for sessions.",
        output_fn=output.append,
        ingest_runner=fake_runner,
    )

    assert result is not None
    assert calls[0][0] == "We chose PostgreSQL for sessions."
    assert calls[0][1] == paths
    assert "input_fn" in calls[0][2]
    assert "output_fn" in calls[0][2]
    assert "Running ingest pipeline..." in output
    assert f"Saved: {saved_path}" in output


def test_repl_log_dispatch_uses_injected_runner(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    values = iter(["/log", "Decision note", "/exit"])
    output: list[str] = []
    calls: list[str] = []

    def input_fn(_prompt: str) -> str:
        return next(values)

    def fake_runner(raw_dump, _paths, **_kwargs):
        calls.append(raw_dump)
        return SimpleNamespace(
            write_result=SimpleNamespace(path=paths.records_dir / "x.md")
        )

    run_repl(
        paths,
        input_fn=input_fn,
        output_fn=output.append,
        log_runner=fake_runner,
    )

    assert calls == ["Decision note"]
    assert "Saved: " + str(paths.records_dir / "x.md") in output


def test_log_command_handles_failed_extraction(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    output: list[str] = []

    def failing_runner(*_args, **_kwargs):
        raise RecordExtractionError(
            "record extraction did not produce a complete record after wrap-up",
            messages=[
                {"role": "assistant", "content": "I still need more details."},
            ],
        )

    result = run_log_command(
        paths,
        input_fn=lambda _prompt: "Decision note",
        output_fn=output.append,
        ingest_runner=failing_runner,
    )

    assert result is None
    assert "Could not turn this session into a complete record." in output
    assert (
        "Nothing was saved. Try /log again with a shorter summary or more context."
        in output
    )
    assert "Last model reply:" in output
    assert "I still need more details." in output


def test_repl_continues_after_log_extraction_failure(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    values = iter(["/log", "Decision note", "/status", "/exit"])
    output: list[str] = []

    def input_fn(_prompt: str) -> str:
        return next(values)

    def failing_runner(*_args, **_kwargs):
        raise RecordExtractionError(
            "record extraction did not produce a complete record after wrap-up",
            messages=[
                {"role": "assistant", "content": "Not a record."},
            ],
        )

    run_repl(
        paths,
        input_fn=input_fn,
        output_fn=output.append,
        log_runner=failing_runner,
    )

    assert "Could not turn this session into a complete record." in output
    assert any(line == "Records: 0" for line in "\n".join(output).splitlines())
