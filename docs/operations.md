# yanka operations runbook

Operational guidance for running and troubleshooting yanka locally.

## Data directory and paths

Resolution precedence:

1. explicit `--data-dir`
2. `config.yaml` `data_dir`
3. `YANKA_DATA_DIR`
4. `~/.yanka`

Important paths under data dir:

- `records/` - source-of-truth markdown
- `graph/`, `vectors/` - rebuildable indexes
- `runtime/yanka.log` - rotated app log
- `runtime/pending_log_session.json` - interrupted `/log` state

## Day-2 commands

## Rebuild indexes

Use when retrieval/conflict warnings suggest stale indexes:

```bash
yanka rebuild
```

Or inside REPL:

```text
/rebuild
```

Expected output:

`Rebuilt indexes from N record(s).`

## Resume interrupted ingest

If `/log` was interrupted:

```text
/resume
```

If no state exists:

`Nothing to resume.`

## Inspect graph/config quickly

Inside REPL:

- `/people`
- `/projects`
- `/config`

## LLM provider and default models

First-run setup writes `llm.provider` and a matching default `llm.model`
(fast/cheap tier). To switch provider later, edit `config.yaml` or delete it
and re-run `yanka` (keychain keys are kept).

| Provider | Default `model` |
|----------|-----------------|
| `claude` | `claude-3-5-haiku-latest` |
| `openai` | `gpt-4o-mini` |
| `google` | `gemini-2.0-flash-lite` |
| `ollama` | `llama3.2:3b` |

Use `/config` to see the effective file contents. API keys are never stored in
the YAML file (keyring or env vars only).

## Troubleshooting

## Generic provider/runtime failures

Check:

`<data_dir>/runtime/yanka.log`

The app logs tracebacks and command context there while keeping terminal output
clean.

## Log growth control

Logging uses rotation:

- 5 MB per file
- 3 backups

Bounded total log footprint is about 20 MB.

## Stale retrieval/index references

Symptom:

- `/ask` warning about missing indexed records and rebuild suggestion.

Action:

1. run `/rebuild`
2. rerun `/ask`

## Recovery and backups

- Back up `records/`, `changelog.jsonl`, and optionally `config.yaml`.
- `graph/` and `vectors/` do not need backup; they are derived from records.

## Test confidence checks

Quick confidence:

```bash
pytest -q
```

Integration matrix:

```bash
pytest tests/integration -q
```
