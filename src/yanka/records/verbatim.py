"""Fence verbatim user/model text so markdown renderers do not reinterpret it."""

from __future__ import annotations

VERBATIM_LANG = "text"


def format_verbatim_block(content: str) -> str:
    """Wrap content in a fenced block (one opening and closing fence only)."""
    text = content.replace("\r\n", "\n").rstrip("\n")
    tick_count = _fence_length(text)
    open_fence = "`" * tick_count + VERBATIM_LANG
    close_fence = "`" * tick_count
    return f"{open_fence}\n{text}\n{close_fence}"


def unwrap_verbatim_section(content: str) -> str:
    """Restore plain text from a saved body section (fenced or legacy blockquote)."""
    stripped = content.strip()
    if stripped.startswith("```"):
        return _unwrap_fenced(stripped)
    return _unwrap_blockquote(stripped)


def _fence_length(content: str) -> int:
    tick_count = 3
    while _fence_marker(tick_count) in content:
        tick_count += 1
    return tick_count


def _fence_marker(tick_count: int) -> str:
    return "`" * tick_count


def _unwrap_fenced(text: str) -> str:
    lines = text.splitlines()
    if not lines:
        return ""

    open_line = lines[0].strip()
    tick_count = 0
    for char in open_line:
        if char == "`":
            tick_count += 1
        else:
            break
    if tick_count < 3:
        return text.strip()

    close_marker = "`" * tick_count
    if lines[-1].strip() == close_marker:
        inner = lines[1:-1]
    else:
        inner = lines[1:]
    return "\n".join(inner).strip()


def _unwrap_blockquote(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(">"):
            stripped = stripped[1:].lstrip()
        lines.append(stripped)
    return "\n".join(lines).strip()
