# Live ingest smoke (`/log`)

Manual verification that `run_ingest_pipeline` and the REPL `/log` command work
with a **real LLM**. OpenAI `gpt-4o-mini` or Gemini Flash are recommended for
cheap structured-output testing.

## Prerequisites

- [ ] `pip install -e ".[dev]"` from the repo root
- [ ] `~/.whyline/config.yaml` exists with:
  ```yaml
  llm:
    provider: openai
    model: gpt-4o-mini
  embedding:
    provider: local
    model: sentence-transformers/all-MiniLM-L6-v2
  ```
- [ ] OpenAI API key in Keychain: service `whyline`, account `openai` (see project README / setup)
- [ ] Verify key: `python -c "from whyline.secrets import get_api_key; print('ok' if get_api_key('openai') else 'missing')"`

## M3 — Happy path (required)

1. Run:
   ```bash
   whyline
   /log
   ```
2. Paste a decision note, e.g.:
   ```text
   We're moving session storage from Redis to PostgreSQL. Carlos owns the migration.
   ```
3. If the model asks clarifying questions, answer in the terminal.
4. If a **Possible conflict** panel appears, you can answer `n` unless you intend to test supersession.

**Pass if:**

- [ ] Green **Record saved** panel appears
- [ ] New file under `~/.whyline/records/*.md` (or your `--data-dir`)
- [ ] Frontmatter includes `record_complete: true`, `context_path`, `decision`, and a `claims` list
- [ ] Extraction used JSON internally; no malformed YAML/frontmatter warning appears
- [ ] `changelog.jsonl` has a new line with `"action": "create"`
- [ ] No traceback; index warnings (if any) mention `whyline rebuild`

Optional sanity:

```bash
whyline rebuild
```

## M4 — Conflict path (optional)

1. Complete M3 once so the graph/vectors have context under e.g. `main-platform/auth-service`.
2. Log a **contradicting** decision in the same area, e.g.:
   ```bash
   python scripts/live_ingest.py "JWT access token lifetime is now 30 minutes, not 15."
   ```
3. When the amber conflict panel appears, answer **`y`** to supersede.

**Pass if:**

- [ ] Written record has `supersedes:` on the matching claim in frontmatter
- [ ] Latest `changelog.jsonl` entry has `"action": "supersede"` and `supersedes_claims`

## Failure notes

| Symptom | What to try |
|--------|-------------|
| API key error | Re-run Keychain setup; check `llm.provider: openai` |
| Invalid JSON record | Prefer `gpt-4o-mini`, Gemini 2.x Flash, or Claude Sonnet; avoid weak local models |
| Index warning only | Record is still saved; run `whyline rebuild` |
| Hang / slow | Normal on first run (local embedding download) |

## Sign-off

- [ ] M3 happy path completed on: ___________
- [ ] M4 conflict (optional) completed on: ___________

When M3 passes, keep **8.3d** ✓ in `IMPLEMENTATION.md`.
