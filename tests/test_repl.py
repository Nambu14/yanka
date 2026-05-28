from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from yanka.ingest.extraction import RecordExtractionError
from yanka.ingest.resume_state import (
    clear_pending_log_session,
    has_pending_log_session,
    save_pending_log_session,
)
from yanka.paths import ensure_data_layout, resolve_data_paths
from yanka.records.io import read_record, write_record
from yanka.repl import (
    HELP_TEXT,
    _build_prompt_adapters,
    _prompt_log_user,
    _read_note_multiline,
    _repl_history_path,
    _slash_commands,
    format_history,
    format_last,
    format_status,
    format_statusline,
    run_ask_command,
    run_log_command,
    run_repl,
    run_resume_command,
)
from yanka.retrieval.output import RetrievalAnswerView
from yanka.ui.pipeline_activity import IngestActivityStage, RetrievalActivityStage

FIXTURE = Path(__file__).parent / "fixtures" / "records" / "valid-decision.md"


def _run_with_inputs(inputs: list[str]) -> list[str]:
    values = iter(inputs)
    output: list[str] = []

    def input_fn(_prompt: str) -> str:
        return next(values)

    run_repl(
        resolve_data_paths(Path("/tmp/yanka-repl-test")),
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

    assert any("Welcome to yanka." in line for line in output)
    assert HELP_TEXT in output
    assert "/ask [question] Query existing knowledge" in HELP_TEXT


def test_repl_quit_exits_cleanly() -> None:
    output = _run_with_inputs(["/quit"])

    assert any("Welcome to yanka." in line for line in output)
    assert all("Unknown command" not in line for line in output)


def test_repl_ignores_empty_input() -> None:
    output = _run_with_inputs(["", "   ", "/exit"])

    assert any("Welcome to yanka." in line for line in output)
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
        resolve_data_paths(Path("/tmp/yanka-repl-eof-test")),
        input_fn=eof_input,
        output_fn=output.append,
    )

    assert any("Welcome to yanka." in line for line in output)


def test_repl_aliases_dispatch_help_history_and_quit(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_record(paths)

    output = _run_with_paths(paths, ["/?", "/h", "/q"])

    assert HELP_TEXT in output
    history = "\n".join(output)
    assert "valid-decision.md" in history


def test_repl_help_topic_log() -> None:
    output = _run_with_inputs(["/help log", "/exit"])
    joined = "\n".join(output)

    assert "/log [text]" in joined
    assert "ingest pipeline" in joined


def test_repl_help_unknown_topic_lists_available() -> None:
    output = _run_with_inputs(["/help bogus", "/exit"])
    joined = "\n".join(output)

    assert "Unknown help topic" in joined
    assert "Topics:" in joined
    assert "log" in joined


def test_repl_inspection_commands_empty_graph(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    output = _run_with_paths(paths, ["/people", "/projects", "/exit"])
    joined = "\n".join(output)

    assert "No people in the graph yet" in joined
    assert "No projects in the graph yet" in joined


def test_repl_config_command(tmp_path: Path) -> None:
    from unittest.mock import patch

    from yanka.config import default_config, save_config

    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    save_config(paths, default_config(paths.data_dir))

    with patch("yanka.secrets.get_api_key", return_value=None):
        output = _run_with_paths(paths, ["/config", "/exit"])

    joined = "\n".join(output)
    assert f"Config file: {paths.config_path}" in joined
    assert "api_key (claude): not set" in joined
    assert "provider: claude" in joined


def test_repl_log_requires_confirmation_when_pending_exists(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    save_pending_log_session(
        paths,
        raw_dump="pending note",
        messages=[{"role": "user", "content": "pending note"}],
    )
    values = iter(["/log new statement", "n", "/exit"])
    output: list[str] = []
    calls: list[str] = []

    def input_fn(_prompt: str) -> str:
        return next(values)

    def fake_runner(raw_dump, _paths, **_kwargs):
        calls.append(raw_dump)
        return SimpleNamespace(
            write_result=SimpleNamespace(path=paths.records_dir / "x.md")
        )

    run_repl(paths, input_fn=input_fn, output_fn=output.append, log_runner=fake_runner)

    assert calls == []
    assert has_pending_log_session(paths)
    assert any("interrupted /log work pending" in line for line in output)


def test_repl_log_discards_pending_when_confirmed(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    save_pending_log_session(
        paths,
        raw_dump="pending note",
        messages=[{"role": "user", "content": "pending note"}],
    )
    values = iter(["/log new statement", "y", "/exit"])
    output: list[str] = []
    calls: list[str] = []

    def input_fn(_prompt: str) -> str:
        return next(values)

    def fake_runner(raw_dump, _paths, **_kwargs):
        calls.append(raw_dump)
        return SimpleNamespace(
            write_result=SimpleNamespace(path=paths.records_dir / "x.md")
        )

    run_repl(paths, input_fn=input_fn, output_fn=output.append, log_runner=fake_runner)

    assert calls == ["new statement"]


def test_resume_command_no_pending(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    output: list[str] = []

    result = run_resume_command(paths, output_fn=output.append)

    assert result is None
    assert "Nothing to resume." in output


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


def test_format_statusline_includes_dir_records_and_llm(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    paths.config_path.write_text(
        "llm:\n  provider: openai\n  model: gpt-4o-mini\n",
        encoding="utf-8",
    )
    _seed_record(paths)

    line = format_statusline(paths)

    assert f"dir: {paths.data_dir.name}" in line
    assert "records: 1" in line
    assert "llm: openai/gpt-4o-mini" in line


def test_format_history_empty_kb(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))

    assert format_history(paths) == "No records yet."


def test_format_last_empty_kb(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    assert format_last(paths) == "No records yet."


def test_repl_history_with_seeded_data(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_record(paths)

    output = _run_with_paths(paths, ["/history", "/exit"])
    history = "\n".join(output)

    assert "2026-05-14" in history
    assert "active" in history
    assert "valid-decision.md" in history
    assert "Drop Redis for session storage" in history


def test_repl_last_with_seeded_data(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_record(paths)

    output = _run_with_paths(paths, ["/last", "/exit"])
    text = "\n".join(output)

    assert "valid-decision.md" in text
    assert "Path: " in text


def test_repl_rebuild_with_seeded_data(tmp_path: Path) -> None:
    from yanka.config import EmbeddingConfig, default_config, save_config
    from yanka.embeddings import EMBEDDING_DIM, register_embedding_backend

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


def test_resume_command_runs_runner_and_clears_pending(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    save_pending_log_session(
        paths,
        raw_dump="pending note",
        messages=[{"role": "user", "content": "pending note"}],
    )
    output: list[str] = []
    calls: list[tuple[str, list[dict[str, str]]]] = []

    def fake_runner(raw_dump, _paths, **kwargs):
        calls.append((raw_dump, kwargs["messages"]))
        return SimpleNamespace(
            write_result=SimpleNamespace(path=paths.records_dir / "resumed.md")
        )

    result = run_resume_command(
        paths,
        output_fn=output.append,
        ingest_runner=fake_runner,
    )

    assert result is not None
    assert calls and calls[0][0] == "pending note"
    assert not has_pending_log_session(paths)
    assert any("Saved:" in line for line in output)


def test_log_command_failure_saves_pending_state(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    clear_pending_log_session(paths)
    output: list[str] = []

    def failing_runner(*_args, **_kwargs):
        raise RecordExtractionError(
            "record extraction did not produce a complete record after wrap-up",
            messages=[{"role": "assistant", "content": "Need details"}],
        )

    run_log_command(
        paths,
        statement="This will fail",
        output_fn=output.append,
        ingest_runner=failing_runner,
    )

    assert has_pending_log_session(paths)
    assert any("run /resume to continue" in line for line in output)


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


def test_log_command_inline_statement_skips_prompt(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    output: list[str] = []
    calls = []
    saved_path = paths.records_dir / "inline.md"

    def fake_runner(raw_dump, runner_paths, **kwargs):
        calls.append((raw_dump, runner_paths, kwargs))
        return SimpleNamespace(write_result=SimpleNamespace(path=saved_path))

    result = run_log_command(
        paths,
        statement="Inline decision note",
        input_fn=lambda _prompt: "should-not-be-used",
        output_fn=output.append,
        ingest_runner=fake_runner,
    )

    assert result is not None
    assert calls[0][0] == "Inline decision note"
    assert "Paste your decision note:" not in output
    assert f"Saved: {saved_path}" in output


def test_log_command_uses_note_reader_when_provided(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    output: list[str] = []
    calls = []

    def fake_runner(raw_dump, _paths, **_kwargs):
        calls.append(raw_dump)
        return SimpleNamespace(
            write_result=SimpleNamespace(path=paths.records_dir / "x.md")
        )

    run_log_command(
        paths,
        input_fn=lambda _prompt: "should-not-be-used",
        note_reader=lambda: "line one\nline two",
        output_fn=output.append,
        ingest_runner=fake_runner,
    )

    assert calls == ["line one\nline two"]
    assert "Paste your decision note:" in output


def test_log_command_calls_ingest_runner_and_reports_saved_path(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    output: list[str] = []
    calls = []
    saved_path = paths.records_dir / "logged.md"

    def fake_runner(raw_dump, runner_paths, **kwargs):
        on_stage = kwargs.get("on_stage")
        if on_stage is not None:
            on_stage(IngestActivityStage.SEARCHING)
            on_stage(IngestActivityStage.EXTRACTING)
            on_stage(IngestActivityStage.VALIDATING)
            on_stage(IngestActivityStage.CONFLICT_CHECK)
            on_stage(IngestActivityStage.WRITING)
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
    assert "· searching for related records..." in output
    assert "· extracting claims..." in output
    assert "· checking for conflicts..." in output
    assert "· writing record..." in output
    assert "on_stage" in calls[0][2]
    assert f"Saved: {saved_path}" in output
    assert "[a] /ask about this" not in "\n".join(output)


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


def test_repl_log_inline_dispatch_uses_injected_runner(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    values = iter(["/log Inline note", "/exit"])
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

    assert calls == ["Inline note"]
    assert "Paste your decision note:" not in output
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


def test_log_prompt_auto_finalizes_on_json_blob(tmp_path: Path) -> None:
    output: list[str] = []
    reply = _prompt_log_user(
        '{"record_complete": true, "decision": "x"}',
        input_fn=lambda _prompt: "",
        output_fn=output.append,
    )

    assert (
        reply == "CONVERSATION ENDED. Output ONLY the final record now — no questions."
    )
    assert "Model returned structured JSON early; finalizing record..." in output


def test_ask_command_with_inline_question(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_record(paths)
    output: list[str] = []
    calls: list[str] = []

    def fake_runner(question, runner_paths, **kwargs):
        on_stage = kwargs.get("on_stage")
        if on_stage is not None:
            on_stage(RetrievalActivityStage.ANALYZING)
            on_stage(RetrievalActivityStage.GRAPH)
            on_stage(RetrievalActivityStage.VECTORS)
            on_stage(RetrievalActivityStage.SYNTHESIZING)
        calls.append(question)
        assert runner_paths == paths
        return SimpleNamespace(
            answer="Sessions use PostgreSQL.",
            answer_view=RetrievalAnswerView(
                answer="Sessions use PostgreSQL.",
                sources=[],
                citations=["with-claims.md"],
                stale_sources=[],
                has_staleness_warning=False,
            ),
        )

    result = run_ask_command(
        paths,
        question="session storage approach",
        output_fn=output.append,
        ask_runner=fake_runner,
        display_answer=lambda retrieval, out: out(retrieval.answer),
    )

    assert result is not None
    assert calls == ["session storage approach"]
    assert "Searching knowledge base..." in output
    assert "· analyzing query..." in output
    assert "· retrieving from graph..." in output
    assert "· retrieving from vectors..." in output
    assert "· synthesizing answer..." in output
    assert "Sessions use PostgreSQL." in output
    assert "[/log to update]  [/ask <follow-up>]" in output


def test_ask_command_prompts_when_question_missing(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_record(paths)
    output: list[str] = []

    def fake_runner(question, _paths, **_kwargs):
        return SimpleNamespace(
            answer=f"Echo: {question}",
            answer_view=RetrievalAnswerView(
                answer=f"Echo: {question}",
                sources=[],
                citations=[],
                stale_sources=[],
                has_staleness_warning=False,
            ),
        )

    run_ask_command(
        paths,
        question="",
        input_fn=lambda _prompt: "What about Redis?",
        output_fn=output.append,
        ask_runner=fake_runner,
        display_answer=lambda retrieval, out: out(retrieval.answer),
    )

    assert "Echo: What about Redis?" in output


def test_ask_command_prints_stale_index_warning(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_record(paths)
    output: list[str] = []

    def fake_runner(_question, _paths, **_kwargs):
        return SimpleNamespace(
            answer="Sessions use PostgreSQL.",
            answer_view=RetrievalAnswerView(
                answer="Sessions use PostgreSQL.",
                sources=[],
                citations=[],
                stale_sources=[],
                has_staleness_warning=False,
            ),
            warnings=[
                "Some indexed records are missing on disk; "
                "run /rebuild to refresh indexes."
            ],
        )

    run_ask_command(
        paths,
        question="session storage approach",
        output_fn=output.append,
        ask_runner=fake_runner,
        display_answer=lambda retrieval, out: out(retrieval.answer),
    )

    assert any(
        "Warning: Some indexed records are missing on disk;" in line for line in output
    )


def test_ask_command_empty_question_does_not_run_pipeline(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    output: list[str] = []
    called = False

    def fake_runner(*_args, **_kwargs):
        nonlocal called
        called = True
        return SimpleNamespace(answer="", answer_view=None)

    run_ask_command(
        paths,
        question="",
        input_fn=lambda _prompt: "   ",
        output_fn=output.append,
        ask_runner=fake_runner,
    )

    assert "Nothing to ask." in output
    assert not called


def test_ask_command_no_records_skips_pipeline(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    output: list[str] = []
    called = False

    def fake_runner(*_args, **_kwargs):
        nonlocal called
        called = True
        return SimpleNamespace(answer="", answer_view=None)

    run_ask_command(
        paths,
        question="anything",
        output_fn=output.append,
        ask_runner=fake_runner,
    )

    assert any("No records yet." in line for line in output)
    assert not called


def test_ask_command_handles_llm_error(tmp_path: Path) -> None:
    from yanka.llm.client import LlmTransportError

    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_record(paths)
    output: list[str] = []

    def failing_runner(*_args, **_kwargs):
        raise LlmTransportError("litellm.InternalServerError: provider down")

    result = run_ask_command(
        paths,
        question="session storage",
        output_fn=output.append,
        ask_runner=failing_runner,
    )

    assert result is None
    assert "Could not answer this question." in output
    joined = "\n".join(output).lower()
    assert "could not reach the llm provider" in joined
    assert "litellm" not in joined
    assert "provider down" not in joined


def test_repl_ask_dispatch_uses_injected_runner(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_record(paths, filename="2026-05-14-valid.md")
    values = iter(["/ask token lifetime", "/exit"])
    output: list[str] = []
    calls: list[str] = []

    def input_fn(_prompt: str) -> str:
        return next(values)

    def fake_runner(question, _paths, **_kwargs):
        calls.append(question)
        return SimpleNamespace(
            answer="30 minutes.",
            answer_view=RetrievalAnswerView(
                answer="30 minutes.",
                sources=[],
                citations=[],
                stale_sources=[],
                has_staleness_warning=False,
            ),
        )

    run_repl(
        paths,
        input_fn=input_fn,
        output_fn=output.append,
        ask_runner=fake_runner,
        display_answer=lambda retrieval, out: out(retrieval.answer),
    )

    assert calls == ["token lifetime"]
    assert "30 minutes." in output


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
    assert "Records: 0" in "\n".join(output)


def test_read_note_multiline_stops_on_blank_line() -> None:
    values = iter(["line 1", "line 2", ""])
    result = _read_note_multiline(lambda _prompt: next(values))
    assert result == "line 1\nline 2"


def test_slash_commands_include_aliases() -> None:
    commands = _slash_commands()
    assert "/log" in commands
    assert "/ask" in commands
    assert "/?" in commands
    assert "/q" in commands
    assert "/last" in commands


def test_repl_history_path_uses_data_dir(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    assert _repl_history_path(paths) == paths.data_dir / "repl_history.txt"


def test_build_prompt_adapters_returns_none_when_prompt_toolkit_missing(
    tmp_path: Path,
) -> None:
    import builtins

    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    real_import = builtins.__import__

    def fail_import(name: str, *args: object, **kwargs: object):
        if name.startswith("prompt_toolkit"):
            msg = "No module named prompt_toolkit"
            raise ImportError(msg)
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", fail_import):
        assert _build_prompt_adapters(paths) is None
