"""REPL constants — spec §11."""

PROMPT = "❯ "

HELP_TEXT = """\
/log [text]     Record a decision (inline or prompted)
/ask [question] Query existing knowledge
/status         Show local KB status
/history        Show recent records
/last           Show most recent record
/people         List people in the graph
/projects       List root projects in the graph
/config         Show effective configuration
/rebuild        Rebuild graph and vector indexes
/resume         Resume interrupted work
/help [topic]   Command reference (e.g. /help log)
/exit           Quit

Aliases: /? -> /help, /h -> /history, /q -> /exit"""
