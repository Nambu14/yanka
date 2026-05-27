from __future__ import annotations

from yanka.ui.system import (
    print_clarifying_panel,
    print_hint,
    print_status_panel,
    print_statusline,
    print_system,
    start_activity,
    yanka_badge,
)


def test_yanka_badge_text() -> None:
    assert str(yanka_badge()) == "yanka"


def test_print_system_and_hint_emit_text() -> None:
    output: list[str] = []

    print_system(output.append, "Welcome")
    print_hint(output.append, "searching...")

    joined = "\n".join(output)
    assert "yanka" in joined
    assert "Welcome" in joined
    assert "searching..." in joined


def test_print_panels_emit_content() -> None:
    output: list[str] = []

    print_clarifying_panel(output.append, "Question 1?\nQuestion 2?")
    print_status_panel(output.append, "Records: 3")

    joined = "\n".join(output)
    assert "Clarifying" in joined
    assert "Question 1?" in joined
    assert "Status" in joined
    assert "Records: 3" in joined


def test_statusline_and_activity_fallback_emit_text() -> None:
    output: list[str] = []

    print_statusline(output.append, "dir: yanka | records: 3")
    activity = start_activity(output.append, "analyzing query...")
    activity.update("retrieving from graph...")
    activity.stop()

    joined = "\n".join(output)
    assert "dir: yanka" in joined
    assert "analyzing query..." in joined
    assert "retrieving from graph..." in joined
