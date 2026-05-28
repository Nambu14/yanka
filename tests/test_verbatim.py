from yanka.records.verbatim import format_verbatim_block, unwrap_verbatim_section


def test_format_and_unwrap_verbatim_block() -> None:
    original = "1. first answer\n2. second answer"
    wrapped = format_verbatim_block(original)

    assert wrapped.startswith("```text\n")
    assert wrapped.endswith("\n```")
    assert "> 1." not in wrapped
    assert unwrap_verbatim_section(wrapped) == original


def test_unwrap_legacy_blockquote_raw_input() -> None:
    legacy = "> line with --- inside\n> ---"
    assert unwrap_verbatim_section(legacy) == "line with --- inside\n---"


def test_format_escapes_nested_backticks() -> None:
    original = "Use ```inline``` carefully"
    wrapped = format_verbatim_block(original)

    assert wrapped.startswith("````text\n")
    assert unwrap_verbatim_section(wrapped) == original
