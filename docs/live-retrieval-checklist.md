# Live retrieval smoke (7.7b)

Manual verification that `run_retrieval_pipeline` works with a **real LLM** and the local graph/vector indexes. Use the REPL (`yanka` → `/ask <question>`) or `scripts/live_ask.py` for a one-shot query.

## Prerequisites

- [ ] `pip install -e ".[dev]"` from the repo root
- [ ] `~/.yanka/config.yaml` exists with a live LLM provider, for example:
  ```yaml
  llm:
    provider: openai
    model: gpt-4o-mini
  embedding:
    provider: local
    model: sentence-transformers/all-MiniLM-L6-v2
  ```
- [ ] API key is configured for the selected provider, for example Keychain service `yanka`, account `openai`
- [ ] Verify key:
  ```bash
  python -c "from yanka.secrets import get_api_key; print('ok' if get_api_key('openai') else 'missing')"
  ```
- [ ] At least one record exists under `~/.yanka/records/`
- [ ] If indexes may be stale, run:
  ```bash
  yanka rebuild
  ```

## M5 — Retrieval happy path (required)

1. Run either:
   ```bash
   yanka
   /ask What's our current approach to session storage?
   ```
   or:
   ```bash
   python scripts/live_ask.py "What's our current approach to session storage?"
   ```
2. Inspect the output panel and hit counts.

**Pass if:**

- [ ] Blue **yanka Answer** panel appears
- [ ] Answer has at least one citation when the local KB has a relevant record
- [ ] Source list includes file/status/date/context metadata
- [ ] Hit counts print after the panel
- [ ] No traceback

## If no local records exist

Seed one record first:

```bash
python scripts/live_ingest.py "We're moving session storage from Redis to PostgreSQL. Carlos owns the migration."
```

Then rerun:

```bash
python scripts/live_ask.py "What's our current approach to session storage?"
```

## Failure notes

| Symptom | What to try |
|--------|-------------|
| API key error | Re-run Keychain setup; check `llm.provider` |
| No hits | Run `yanka rebuild`; check records under `~/.yanka/records/` |
| Empty answer with hits | Capture Prompt 5 output and tune synthesis later |
| Slow first run | Normal if local embedding model downloads |

## Sign-off

- [ ] Retrieval happy path completed on: ___________

When this passes, mark **7.7b** ✓ in `IMPLEMENTATION.md`.
