# Phase 9 — Wrap-up plan (source of truth)

This document captures the **approved Phase 9 scope** (architectural review, code review, UX review, and implementation slices). Use it when continuing work in a fresh Cursor workspace or after renaming the repo — it replaces reliance on chat history.

**Spec:** [`yanka-spec.md`](../yanka-spec.md) §11 (CLI UX), §12 (Error handling)  
**Tracker:** [`IMPLEMENTATION.md`](../IMPLEMENTATION.md) Phase 9 rows  
**Deferred ideas:** [`future-improvements.md`](future-improvements.md)

**Prerequisite:** Phase **R.0** (rename to yanka) is complete.

---

## Goal

Ship **v1** by closing gaps between as-built code and the spec: error handling, REPL polish, inspection commands, code structure, integration tests, docs, and one live smoke. This is the final implementation phase before post-v1 items in `future-improvements.md`.

**Milestone:** Satisfy **M6** exit criteria in `IMPLEMENTATION.md` (REPL, resume, spec §12 errors, manual `/log` + `/ask`).

---

## Reviews (findings to address in 9.x)

### Architecture

| Finding | Severity | Address in |
|---------|----------|------------|
| `repl.py` (~640 LoC) mixes dispatch, runners, Rich, prompt_toolkit | Medium | 9.6 |
| Post-extraction failures (entity resolution, conflict eval) abort instead of degrading; record can be lost after extraction succeeded | High | 9.2 |
| Resume state only covers extraction-stage failures, not later pipeline stages | High | 9.2 |
| LLM errors flattened to `LlmError(str)` — no retry / no user-friendly mapping | High | 9.1, 9.3 |
| LiteLLM import-time warnings (`botocore`, etc.) before runtime config | Low | 9.1 |
| No app log file for post-mortems | Low | 9.9 |
| No first-class graph inspection (`/people`, etc.) | Medium | 9.5 |
| Cypher built via f-strings; double MERGE+SET round trips per entity | Medium | 9.7 |

**Invariants to preserve:** Markdown first; `yanka rebuild` recovers indexes; app orchestrates, LLM does not.

### Code

| Finding | Address in |
|---------|------------|
| Duplicate `_ConsoleFile` in `repl.py` and `ui/system.py` | 9.6 |
| `_run_live_log` / `_run_live_resume` nearly identical | 9.6 |
| `format_statusline` scans all records every prompt | 9.6 |
| `load_retrieved_records` raises if file missing on disk (stale index) | 9.8 |
| `click.prompt` without `default=""` caused API key loop (fixed in setup) | Done |

### UX (spec §11)

| Finding | Address in |
|---------|------------|
| Activity spinner stages fire back-to-back before work starts | 9.4 |
| Provider errors shown raw (`litellm.InternalServerError...`) | 9.3 |
| `click.confirm` prints `Aborted!` on Ctrl+C during conflicts | 9.3 |
| Quick-action footers `[a]/[o]/[n]` imply keys that don't exist | 9.4 |
| Welcome screen plain text vs spec richness | 9.4 |
| No `/people`, `/projects`, `/config` | 9.5 |

### Already in good shape

- JSON extraction + strict schema + wrap-up (`8.3d`)
- Session transcript (`raw_input`, `clarifying_exchange`) in Python (`8.3e`)
- `/resume` + pending session file (`8.6`)
- Index failure after write → warning + rebuild hint (`write.py`, ingest confirm panel)
- Claim validation degrades with amber warning

---

## Implementation slices (order)

Execute **one step at a time** per `IMPLEMENTATION.md` working agreement: plan → approve → implement → verify → report.

```
R.0 ✓ → 9.0 ✓ → 9.1 ✓ → 9.2 ✓ → 9.3 ✓ → 9.4 ✓ → 9.5 ✓ → 9.6 ✓ → 9.7 ✓ → 9.8 ✓ → 9.9 ✓ → 9.10 ✓ → 9.11 ✓ → 9.11b ✓ → 9.11c ✓ → 9.12
```

| ID | Title | Deliverable summary |
|----|--------|---------------------|
| **9.0** | Reviews committed | This file + `IMPLEMENTATION.md` rows (no product code) |
| **9.1** | Typed `LlmError` + retry-once + import-time LiteLLM quiet | `LlmTransportError`, `LlmAuthError`, `LlmRateLimitError`, `LlmTimeoutError`; one silent retry on transient; suppress warnings before `import litellm` |
| **9.2** | Post-extraction degrade + resume by stage | Entity/conflict LLM failures degrade; write record when extraction succeeded; `pending_log_session` includes `stage` |
| **9.3** | REPL error mapper + `click.Abort` | `repl/errors.py` maps exceptions → spec §12 messages; no raw litellm strings |
| **9.4** | Real progress + welcome panel | `on_stage` callback on pipelines; spinner follows stages; welcome Rich panel; fix footers |
| **9.5** | Inspection commands | `/people`, `/projects`, `/config`, `/help <cmd>` |
| **9.6** | `repl/` package split | Pure refactor: `repl/commands/`, `format.py`, `prompts.py`; dedupe `_ConsoleFile`; cache record count |
| **9.7** | Cypher hardening | Safer escape or parameters; `MERGE … ON CREATE SET … ON MATCH SET` |
| **9.8** | Stale index resilience | Skip missing record files in synthesis; warn + suggest `/rebuild` |
| **9.9** | Application logging | `~/.yanka/runtime/yanka.log`, silenced in tests |
| **9.10** | Integration tests | `tests/integration/` with real LanceDB + LadybugDB, mocked LLM |
| **9.11** | Docs refresh | README quickstart, `docs/architecture.md`, `docs/operations.md` |
| **9.11b** | Spec refresh | Truth-up `yanka-spec.md` §2/§6/§7/§8/§11/§12/§14 to match as-built v1 (no code changes) |
| **9.11c** | Lint sweep | `line-length = 120` in `pyproject.toml`; fix import order + `session_transcript` E402 |
| **9.12** | Live smoke (M6 gate) | `docs/live-m6-checklist.md` — real provider `/log` + `/ask` |

---

## Per-step notes (for planning)

### 9.1 — LLM layer

- Classify litellm exceptions in `_call_litellm`.
- `send_messages` / `fetch_typed_json`: one retry on transport/timeout/rate-limit.
- Set `LITELLM_LOG=ERROR` (or equivalent) **before** importing litellm.

### 9.2 — Never lose data after extraction

- `evaluate_conflicts` / entity resolution: on `LlmError`, degrade (empty conflicts / new context branch) + warning.
- If `Record` exists from extraction, call `write_ingested_record` even when later step fails (with warnings).
- Extend `PendingLogSession` with optional `stage: str` for `/resume`.

### 9.3 — User-facing errors

Example mapping:

| Failure | Message shape |
|---------|----------------|
| Network / 5xx | Can't reach provider; check connection; `/resume` |
| Auth | API key rejected; keyring/env; `/resume` |
| Rate limit | Wait and `/resume` |
| Timeout | No response in 45s; `/resume` |
| Other | See `yanka.log`; `/resume` |

Catch `click.Abort` in REPL conflict path.

### 9.4 — UX

- `run_ingest_pipeline(..., on_stage: Callable[[str], None] | None = None)`.
- Stages: `searching` → `extracting` → `validating` → `conflict-check` → `writing`.
- Retrieval: `analyzing` → `graph` → `vectors` → `synthesizing`.

### 9.5 — Inspection

- `/people`: Cypher `MATCH (p:Person) RETURN p.name, p.aliases` + decision counts if easy.
- `/projects`: root `Context` nodes + record counts.
- `/config`: effective `YankaConfig` (no secrets).

### 9.10 — Integration test matrix

| Scenario | Assert |
|----------|--------|
| `/log` happy (mocked LLM) | markdown + graph + vectors |
| Conflict supersession | graph supersede edge |
| `/ask` happy | answer + citations |
| Stale vector index | skip missing file, warn |
| `/resume` after extraction error | pending file kept |
| Index fail after write | file exists, warning |
| `/rebuild` | recovers search |

### 9.12 — Live smoke

Manual checklist: fresh install → wizard → `/log` → `/ask` → `/rebuild` → interrupt → `/resume`.

---

## Out of scope (Phase 9)

- Person alias management → `future-improvements.md`
- Multi-record session splitting (beyond LLM behavior today)
- Per-provider prompt tuning, retrieval session memory, `wl` alias, `yanka merge`, cloud/multi-user

---

## Verification standard (every 9.x step)

```bash
pip install -e ".[dev]"
pytest tests/<targeted>.py -q   # step-specific
pytest -q
ruff check src tests
```

---

## Cursor / chat history

If the workspace folder was renamed (`whyline` → `yanka`), Cursor may use a new project id. To recover chats or keep one project id, run:

```bash
./scripts/migrate_cursor_chats.sh
```

See script header for symlink alternative.

---

## Approval

Phase 9 scope was approved in chat. **9.0** is committed in-repo. Next: **`approve 9.1`** for the first code step (typed `LlmError` + retry + LiteLLM import quiet).
