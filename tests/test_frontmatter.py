from pathlib import Path

from whyline.records.frontmatter import (
    parse_frontmatter,
    parse_record_markdown,
    split_markdown,
)

FIXTURES = Path(__file__).parent / "fixtures" / "records"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_valid_decision_parses_top_frontmatter_only() -> None:
    text = _read("valid-decision.md")
    frontmatter, body = split_markdown(text)

    assert frontmatter is not None
    assert frontmatter["date"].isoformat() == "2026-05-14"
    assert frontmatter["decision"] == "Drop Redis for session storage"
    assert "user pasted --- here" in body
    assert body.count("---") >= 1


def test_invalid_yaml_returns_none() -> None:
    assert parse_frontmatter(_read("invalid-yaml.md")) is None


def test_no_opening_fence_returns_none() -> None:
    frontmatter, body = split_markdown(_read("no-fence.md"))
    assert frontmatter is None
    assert "no frontmatter" in body


def test_unclosed_fence_returns_none() -> None:
    assert parse_frontmatter(_read("unclosed-fence.md")) is None


def test_bare_fences_not_frontmatter() -> None:
    text = "---\n---\n"
    assert parse_frontmatter(text) is None


def test_leading_whitespace_before_fence() -> None:
    text = "  \n---\ndate: 2026-05-14\n---\n"
    frontmatter, body = split_markdown(text)
    assert frontmatter is not None
    assert frontmatter["date"].isoformat() == "2026-05-14"
    assert body == ""


def test_empty_yaml_block_is_not_valid_frontmatter() -> None:
    text = "---\n---\n\n## Body\n"
    frontmatter, body = split_markdown(text)
    assert frontmatter is None
    assert body == text


def test_non_mapping_yaml_returns_none() -> None:
    text = "---\n- list item\n---\n"
    assert parse_frontmatter(text) is None


def test_parse_record_markdown_alias() -> None:
    text = _read("valid-decision.md")
    assert parse_record_markdown(text) == split_markdown(text)


def test_horizontal_rule_in_body_not_parsed_as_second_block() -> None:
    text = "---\ntype: decision\n---\n\n## A\n\n---\n\n## B\n"
    frontmatter, body = split_markdown(text)
    assert frontmatter == {"type": "decision"}
    assert "## A" in body and "## B" in body
