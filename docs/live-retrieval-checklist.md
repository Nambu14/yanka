# Live retrieval smoke (7.7b)

Manual verification that `run_retrieval_pipeline` works with a **real LLM** and the local graph/vector indexes. There is no `/ask` REPL yet (Phase 8); use `scripts/live_ask.py` for a one-shot query.

## Prerequisites

- [ ] `pip install -e ".[dev]"` from the repo root
- [ ] `~/.whyline/config.yaml` exists with a live LLM provider, for example:
  ```yaml
  llm:
    provider: openai
    model: gpt-4o-mini
  embedding:
    provider: local
    model: sentence-transformers/all-MiniLM-L6-v2
  ```
- [ ] API key is configured for the selected provider, for example Keychain service `whyline`, account `openai`
- [ ] Verify key:
  ```bash
  python -c "from whyline.secrets import get_api_key; print('ok' if get_api_key('openai') else 'missing')"
  ```
- [ ] At least one record exists under `~/.whyline/records/`
- [ ] If indexes may be stale, run:
  ```bash
  whyline rebuild
  ```

## M5 — Retrieval happy path (required)

1. Run:
   ```bash
   python scripts/live_ask.py "What's our current approach to session storage?"
   ```
2. Inspect the output panel and hit counts.

**Pass if:**

- [ ] Blue **whyline Answer** panel appears
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
| No hits | Run `whyline rebuild`; check records under `~/.whyline/records/` |
| Empty answer with hits | Capture Prompt 5 output and tune synthesis later |
| Slow first run | Normal if local embedding model downloads |

## Sign-off

- [ ] Retrieval happy path completed on: ___________

When this passes, mark **7.7b** ✓ in `IMPLEMENTATION.md`.
