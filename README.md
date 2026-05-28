# yanka

Capture engineering decisions from natural conversation, turn them into
structured records, and retrieve them later with natural language.

## What yanka does

- Converts free-form `/log` notes into structured markdown decision records.
- Indexes records into a local graph + vector store for retrieval.
- Answers `/ask` questions with citations to matching records.
- Keeps markdown files as the source of truth; indexes are disposable and
  recoverable with `/rebuild`.

## Install

```bash
pip install -e ".[dev]"
```

## First run

```bash
yanka
```

On first run, yanka initializes your data directory (default `~/.yanka`) and
walks through provider/key setup.

## Data layout

```
~/.yanka/
├── records/                # Markdown records (source of truth)
├── changelog.jsonl         # Append-only record operations
├── graph/                  # LadybugDB index (rebuildable)
├── vectors/                # LanceDB index (rebuildable)
├── runtime/                # runtime logs and pending resume state
└── config.yaml             # effective configuration
```

## Core commands (REPL)

- `/log [text]` - record a decision (inline or prompted)
- `/ask [question]` - query indexed knowledge
- `/resume` - continue interrupted `/log`
- `/rebuild` - rebuild graph/vector indexes from markdown files
- `/status`, `/history`, `/last` - inspect local records
- `/people`, `/projects`, `/config` - inspect graph/config state
- `/help [topic]` - command help
- `/exit` - quit

## Common recovery flows

- **Stale index warning in `/ask`**
  - Run `/rebuild`, then retry `/ask`.
- **Interrupted logging session**
  - Run `/resume`.
- **Unexpected provider/runtime error**
  - Check `~/.yanka/runtime/yanka.log` (rotated, bounded file logs).

## Logging

yanka writes application logs to `runtime/yanka.log` in your data directory
with rotation:

- `maxBytes=5_000_000`
- `backupCount=3`

## Documentation

- Implementation tracker: [`IMPLEMENTATION.md`](IMPLEMENTATION.md)
- Phase 9 wrap-up scope: [`docs/phase-9-wrap-up.md`](docs/phase-9-wrap-up.md)
- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Operations runbook: [`docs/operations.md`](docs/operations.md)
- Future ideas: [`docs/future-improvements.md`](docs/future-improvements.md)
