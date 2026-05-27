"""REPL text formatting for graph inspection commands."""

from __future__ import annotations

from yanka.graph.inspect import PersonSummary, ProjectSummary

_EMPTY_GRAPH_HINT = "Use /log, then /rebuild if indexes are stale."


def format_people(people: list[PersonSummary]) -> str:
    if not people:
        return f"No people in the graph yet. {_EMPTY_GRAPH_HINT}"
    lines: list[str] = []
    for person in people:
        alias_text = ", ".join(person.aliases) if person.aliases else "—"
        lines.append(
            f"{person.name}  aliases: {alias_text}  decisions: {person.decision_count}"
        )
    return "\n".join(lines)


def format_projects(projects: list[ProjectSummary]) -> str:
    if not projects:
        return f"No projects in the graph yet. {_EMPTY_GRAPH_HINT}"
    return "\n".join(
        f"{project.canonical_name}  records: {project.decision_count}"
        for project in projects
    )
