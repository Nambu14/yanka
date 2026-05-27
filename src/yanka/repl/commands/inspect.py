"""REPL inspection commands — /people, /projects, /config."""

from __future__ import annotations

from yanka.config import format_config_display
from yanka.graph import GraphStoreError, get_graph_db
from yanka.graph.inspect import list_people, list_projects
from yanka.paths import DataPaths
from yanka.repl.format_inspect import format_people, format_projects
from yanka.repl.types import OutputFn


def run_people_command(
    paths: DataPaths,
    *,
    output_fn: OutputFn | None = None,
) -> None:
    output = output_fn if output_fn is not None else print
    try:
        graph = get_graph_db(paths)
        people = list_people(graph)
    except GraphStoreError as exc:
        output(str(exc))
        return
    output(format_people(people))


def run_projects_command(
    paths: DataPaths,
    *,
    output_fn: OutputFn | None = None,
) -> None:
    output = output_fn if output_fn is not None else print
    try:
        graph = get_graph_db(paths)
        projects = list_projects(graph)
    except GraphStoreError as exc:
        output(str(exc))
        return
    output(format_projects(projects))


def run_config_command(
    paths: DataPaths,
    *,
    output_fn: OutputFn | None = None,
) -> None:
    output = output_fn if output_fn is not None else print
    output(format_config_display(paths))
