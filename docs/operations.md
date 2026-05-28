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
