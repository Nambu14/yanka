"""Per-command help text for ``/help <topic>``."""

from __future__ import annotations

_TOPICS: dict[str, str] = {
    "log": """\
/log [text]  Record a decision

Paste or type a brain dump (inline text after /log, or prompted).
Runs the ingest pipeline: extraction, claims, conflicts, write.

Related: /resume (interrupted /log), /rebuild (refresh indexes)""",
    "ask": """\
/ask [question]  Query existing knowledge

Runs retrieval over graph + vectors and shows a synthesized answer.
Requires at least one record; use /log first.

Related: /rebuild if answers look stale""",
    "status": """\
/status  Show local knowledge-base status

Record count, projects (from files), and latest record date.""",
    "history": """\
/history  Show recent records

Lists the five most recent markdown records with date and summary.
Alias: /h""",
    "last": """\
/last  Show the most recent record

Filename, decision summary, and full path.""",
    "rebuild": """\
/rebuild  Rebuild graph and vector indexes

Re-indexes all markdown records on disk. Use after manual file edits
or when /ask or conflict search warns about stale indexes.""",
    "resume": """\
/resume  Resume interrupted /log work

Continues from saved pending state after extraction or ingest errors.""",
    "people": """\
/people  List people in the graph

Shows Person nodes and how many decisions involve each person.""",
    "projects": """\
/projects  List root projects in the graph

Shows top-level Context nodes (depth 0) and decision counts per subtree.""",
    "config": """\
/config  Show effective configuration

Displays config.yaml settings (no API keys). Reports whether each
provider key is set in keyring or environment.""",
    "help": """\
/help [topic]  Command reference

Without a topic, lists all commands. With a topic (e.g. /help log),
shows detailed usage for that command.""",
    "exit": """\
/exit  Quit the REPL

Aliases: /quit, /q""",
}


def normalize_help_topic(raw: str) -> str:
    return raw.strip().lstrip("/").lower()


def format_help_topic(topic: str) -> str | None:
    return _TOPICS.get(normalize_help_topic(topic))


def list_help_topics() -> list[str]:
    return sorted(_TOPICS)
