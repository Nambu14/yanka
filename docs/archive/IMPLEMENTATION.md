# Yanka — Implementation Plan (archived)

Historical step-by-step build plan for v1. **Implementation is complete** (Phases
0–9 and **R.0**). For current behavior, use [`yanka-spec.md`](../../yanka-spec.md)
and [`docs/architecture.md`](../architecture.md).

Each step was one PR-sized (or smaller) unit: implement → verify → move on.

---

## Milestones

| ID | You can… |
|----|----------|
| **M0** | Run `yanka` and get a data dir + config |
| **M1** | Write/read a record file + changelog |
| **M2** | `yanka rebuild` rebuilds graph + vectors from files alone |
| **M3** | `/log` end-to-end without conflicts (happy path) |
| **M4** | `/log` with conflict detection + supersession |
| **M5** | `/ask` returns a cited answer |
| **M6** | Full spec UX (resume, error paths, polish) |

### Milestone exit criteria

Do not advance until every bullet passes.

| Milestone | Exit criteria |
|-----------|----------------|
| **M0** | `pip install -e ".[dev]"` succeeds; `pytest` green; `yanka --version` works; fresh data dir has `records/`, `graph/`, `vectors/`; `config.yaml` load/save round-trips; API key read/write via keyring or env; first-run wizard writes config (manual smoke OK). |
| **M1** | Fixture records parse and round-trip; `write_record` + `iter_records` + `append_changelog` tested; no LLM/DB required. |
| **M2** | With only markdown files on disk, `rebuild` repopulates graph + vectors; vector search returns expected fixture; corrupting `vectors/` and rebuilding recovers. |
| **M3** | `/log` (or `ingest_pipeline` in test) produces a valid markdown file + indexes; mocked LLM only; no conflict branch. |
| **M4** | Same as M3 plus conflict candidates → user confirm → supersession written to file + graph + changelog. |
| **M5** | `/ask` (or `retrieval_pipeline` in test) returns answer with citations from fixture KB; mocked LLM. |
| **M6** | REPL commands work; resume after interrupt; error messages match spec §12; one manual happy-path `/log` + `/ask` with real API key (optional checklist). |

---

## Architecture

```
CLI (REPL) ──► Config + keyring
     │
     ├── Ingest pipeline ──► LLM (LiteLLM)
     │         ├── Filesystem (source of truth)
     │         ├── LadybugDB (graph, disposable)
     │         └── LanceDB (vectors, disposable)
     │
     └── Retrieval pipeline ──► same stores + LLM
```

**Invariant:** Markdown is written first. Graph and vectors are rebuilt from files via `yanka rebuild`.

---

## Dependencies (confirmed)

| Package | Install | Purpose |
|---------|---------|---------|
| click | `pip install click` | CLI |
| rich | `pip install rich` | Terminal UI |
| litellm | `pip install litellm` | LLM providers |
| fastembed | `pip install fastembed` | Local embeddings |
| **ladybug** | **`pip install ladybug`** | **Embedded graph DB (LadybugDB)** |
| lancedb | `pip install lancedb` | Vector store |
| pyyaml | `pip install pyyaml` | Record frontmatter |
| keyring | `pip install keyring` | API keys |

Validate imports/APIs in **Phase S** before building indexes on them. Ladybug: `Database`, `Connection`, Cypher via `conn.execute()` — [Python docs](https://docs.ladybugdb.com/client-apis/python/).

---

## Module layout (target)

```
src/yanka/
  cli/           # entry, repl, commands
  config.py
  paths.py
  records/       # parse, validate, io, changelog
  embeddings.py
  vectors/       # lancedb
  graph/         # ladybug
  llm/           # client, prompts, json
  ingest/
  retrieval/
  ui/            # rich components
  rebuild.py
```

---

## Phase 0 — Project skeleton → M0

| Step | Task | Deliverable | Verify | Status |
|------|------|-------------|--------|--------|
| 0.1 | Package layout | `pyproject.toml`, `src/yanka/` | `pip install -e .` | ✓ |
| 0.2 | CLI entry (shell) | `yanka --help` | Console script works | ✓ |
| 0.3 | Paths module | `data_dir`, `records/`, `graph/`, `vectors/`, paths | Unit test with `tmp_path` | ✓ |
| 0.3b | Data dir override | `YANKA_DATA_DIR` env; `--data-dir` CLI flag | Tests/dev never touch real `~/.yanka` | ✓ |
| 0.4 | Bootstrap data dir | `ensure_data_layout()` | Tree matches spec §2 | ✓ |
| 0.5 | Config load/save | `load_config()`, `save_config()` | YAML round-trip | ✓ |
| 0.6 | API key storage | keyring + env fallback | Mocked tests | ✓ |
| 0.7 | First-run wizard | provider + key + data dir | Fresh `~/.yanka` works | ✓ |

**Note:** User-facing `data_dir` (first-run choice) lands in **0.5** (config) + **0.7** (wizard). Resolution order will become: CLI `--data-dir` → `config.data_dir` → `YANKA_DATA_DIR` → `~/.yanka`.

---

## Phase S — Dependency spikes (before indexes)

Run once before Phase 2–3 implementation. Small scripts or tests under `tests/spikes/` (or `scripts/spikes/`); not shipped as product features.

| Step | Task | Deliverable | Verify |
|------|------|-------------|--------|
| S.1 | Ladybug spike | import, create DB, one node + edge, one Cypher query | Script/test runs locally (and CI if feasible) |
| S.2 | LanceDB spike | import, create table, insert + vector/text query | Same |
| S.3 | LiteLLM spike | import, one `completion` call (mock or skip without API key) | Import works; optional live smoke |

**Gate:** All three spikes pass before starting Phase 2.4+ / 3.2+.

**Done:** `tests/spikes/` + optional dep group `spike`. Default `pytest` skips `tests/spikes/` via `norecursedirs`; run spikes with `pip install -e ".[spike]"` and `YANKA_RUN_SPIKES=1 pytest tests/spikes`.

---

## Phase 1 — Record model (filesystem only) → M1

No LLM, no DBs. Use `YANKA_DATA_DIR` / `--data-dir` in all tests.

| Step | Task | Deliverable | Verify |
|------|------|-------------|--------|
| 1.1 | Frontmatter parser | `parse_frontmatter()` | Valid / invalid fixtures | ✓ |
| 1.2 | Completion check | `is_complete_record()` | Spec §7 key set | ✓ |
| 1.3 | Record datatypes | `Record`, `Claim` | Parse spec §3 example | ✓ |
| 1.4 | Filename / slug | `YYYY-MM-DD-<slug>.md` | Collision policy tested | ✓ |
| 1.5 | Serialize to markdown | `record_to_markdown()` | Round-trip | ✓ |
| 1.6 | Write record | `write_record()` | File on disk | ✓ |
| 1.7 | Read all records | `iter_records()` | Multi-file fixture | ✓ |
| 1.8 | Changelog append | `append_changelog()` | JSONL + stable hash | ✓ |

---

## Phase 2 — Embeddings + vector store

| Step | Task | Deliverable | Verify |
|------|------|-------------|--------|
| 2.1 | `embed()` abstraction | `embed(texts) -> vectors` | Interface test | ✓ |
| 2.2 | FastEmbed backend | all-MiniLM-L6-v2 | 384-dim output | ✓ |
| 2.3 | LanceDB helper | `get_vector_db()` | Idempotent open | ✓ |
| 2.4 | Records table | spec §5 schema | Empty query | ✓ |
| 2.5 | Claims table | spec §5 schema | Manual insert | ✓ |
| 2.6 | Index one record | `index_record()` | Semantic hit | ✓ |
| 2.7 | Index claims | `index_claims()` | Claim wording hit | ✓ |
| 2.8 | Search helpers | filters: status, project, context | Filter unit tests | ✓ |

---

## Phase 3 — Graph store (LadybugDB)

**Package:** `pip install ladybug` (not Kuzu). Phase **S.1** must pass first.

| Step | Task | Deliverable | Verify |
|------|------|-------------|--------|
| 3.1 | Spike → production helper | fold S.1 into `get_graph_db()` | Idempotent open at `graph/` | ✓ |
| 3.2 | Schema init | Context, Decision, Claim, Person + edges | Insert each type | ✓ |
| 3.3 | Context path upsert | `contains` hierarchy | Idempotent re-run | ✓ |
| 3.4 | Decision + edges | `about`, `involves`, `has_claim` | Query returns links | ✓ |
| 3.5 | Supersede edges | claim → claim, status updates | Chain query | ✓ |
| 3.6 | Graph conflict candidates | subtree active claims | Fixture graph | ✓ |

*(Former 3.2–3.7 renumbered after folding spike into 3.1.)*

---

## Phase 4 — Rebuild → M2

| Step | Task | Deliverable | Verify |
|------|------|-------------|--------|
| 4.1 | Reset indexes | wipe `graph/`, `vectors/` only | Dirs recreated | ✓ |
| 4.2 | Rebuild from files | parse → graph → vectors | Search works post-rebuild | ✓ |
| 4.3 | CLI `/rebuild` | user-facing command | Corrupt vectors → recover | ✓ |

---

## Phase 5 — LLM layer

| Step | Task | Deliverable | Verify |
|------|------|-------------|--------|
| 5.1 | LiteLLM wrapper | `send_messages(messages, ...)` | Mock + optional live | ✓ |
| 5.2 | Prompt registry | 5 prompts from spec §10 | `get_prompt(name)` | ✓ |
| 5.3 | JSON helper | parse fenced JSON, retry | Malformed fixtures | ✓ |

---

## Phase 6 — Ingest pipeline → M3, M4

Build bottom-up: write path first, then conversation, then intelligence.

| Step | Task | Spec ref | Verify |
|------|------|----------|--------|
| 6.1 | Write pipeline | step 9 | File written if vector fails | ✓ |
| 6.2 | Confirmation UI | step 10 | Rich panel smoke | ✓ |
| 6.3 | Claim extraction | prompt 2 | Mock JSON → claims | ✓ |
| 6.4 | Claim validation | step 4 | pass / retry / amber | ✓ |
| 6.5 | Context search | step 1 | Related record in prompt | ✓ |
| 6.6 | Extraction loop | step 2 | Mock: Q&A then record | ✓ |
| 6.7 | Entity resolution v1 | step 5 | normalized exact match only | ✓ |
| 6.8 | Entity resolution v2 | §9 | aliases + LLM + user ask | ✓ |
| 6.9 | Conflict candidates | step 6 | vector + graph merge | ✓ |
| 6.10 | Conflict evaluation | step 7, prompt 3 | Mock conflicts | ✓ |
| 6.11 | User confirmation | step 8 | yes/no per conflict | ✓ |
| 6.12a | Ingest orchestrator (mocked) | steps 1–10 | `pytest` E2E with mocked LLM; no network | ✓ |
| 6.12b | Ingest orchestrator (live) | steps 1–10 | REPL `/log` + pipeline tests | ✓ |

**Gate:** 6.12a must pass before 6.12b.

---

## Phase 7 — Retrieval pipeline → M5

| Step | Task | Verify |
|------|------|--------|
| 7.1 | Query analysis (prompt 4) | Per query-type fixtures | ✓ |
| 7.2 | Graph retrieve by type | §8 table | ✓ |
| 7.3 | Vector retrieve by type | Filters from analysis | ✓ |
| 7.4 | Graph-anchored merge | Superseded trap case | ✓ |
| 7.5 | Synthesis (prompt 5) | Mock with record bundle | ✓ |
| 7.6 | Output formatting | citations, timeline, staleness | ✓ |
| 7.7a | Retrieval orchestrator (mocked) | `pytest` E2E with mocked LLM | ✓ |
| 7.7b | Retrieval orchestrator (live) | One manual `/ask` with real API key | ✓ |

**Gate:** 7.7a must pass before 7.7b.

---

## Phase 8 — Interactive CLI → M6

| Step | Task | Verify |
|------|------|--------|
| 8.1 | REPL loop | `/help` | ✓ |
| 8.2 | `/status`, `/history`, `/rebuild` | Seeded data | ✓ |
| 8.3 | `/log` REPL command | Mocked ingest session | ✓ |
| 8.3a-c | `/log` extraction hardening | No traceback; explicit format | ✓ |
| 8.3d | JSON record extraction contract | LLM JSON → `Record` → Markdown | ✓ |
| 8.3e | Session transcript in record body | Python `Raw input` + `Clarifying exchange` | ✓ |
| 8.4 | `/ask` | Answer from KB | ✓ |
| 8.5a | Rich UX polish (visual patterns) | spec §11 checklist | ✓ |
| 8.5b | REPL input engine (prompt_toolkit) | multiline paste, completion, history | ✓ |
| 8.5c | Statusline + advanced UX affordances | persistent context and power flows | ✓ |
| 8.6 | `/resume` | interrupt → resume | ✓ |

---

## Phase R — Rename (pre–Phase 9)

| Step | Task | Verify |
|------|------|--------|
| R.0 | Rename `whyline` → `yanka` (package, CLI, paths, docs; no legacy migration) | `yanka --version`; `pytest -q`; `rg -i whyline` empty | ✓ |

---

## Phase 9 — Wrap-up (hardening, polish, coverage)

| Step | Topic | Verify |
|------|--------|--------|
| 9.0 | Reviews + plan in repo | wrap-up scope captured in repo | ✓ |
| 9.1 | Typed `LlmError` + retry-once + LiteLLM import quiet | unit tests per error class | ✓ |
| 9.2 | Post-extraction failure → save state + degrade | resume tests per stage | ✓ |
| 9.3 | REPL error mapper + `click.Abort` containment | REPL error snapshots | ✓ |
| 9.4 | Real-progress activity + welcome panel + footers | REPL / pipeline tests | ✓ |
| 9.5 | `/people`, `/projects`, `/config`, `/help <cmd>` | command tests | ✓ |
| 9.6 | `repl/` split + dedupe (pure refactor) | existing tests unchanged | ✓ |
| 9.7 | Cypher hardening + fewer round trips | fuzz / graph tests | ✓ |
| 9.8 | `/ask` resilient to stale indexes | integration case | ✓ |
| 9.9 | Application logging (`runtime/yanka.log`) | log file + test silence | ✓ |
| 9.10 | Broad integration tests (real DBs, mocked LLM) | `tests/integration/` | ✓ |
| 9.11 | README + architecture + operations docs | manual review | ✓ |
| 9.11b | Spec refresh (post-Phase-9 drift): §2 runtime/, §6 defaults, §7/§8 notes, §11 commands, §12 errors, §14 decisions | manual review | ✓ |
| 9.11c | Lint sweep: `line-length = 120`, import order, `session_transcript` E402 | `ruff check src tests` | ✓ |
| 9.12 | Live smoke (M6 exit) | manual `/log` + `/ask` with real provider | |
| 9.13 | Per-claim duplicate guard (drop restated claims; raise `IngestDuplicateRecordError` when all duplicate) | `tests/test_duplicate_claims.py`, pipeline scenarios | ✓ |

**Also covers (from original 9.x):** malformed record wrap-up (8.3d), index fail warn (6.1), no user tracebacks (9.3).

*(Data-dir override moved to **0.3b** — not deferred here.)*

---

## Deferred (not v1)

- See `docs/future-improvements.md` for tracked post-v1 enhancements.
- Cloud / multi-user
- `yanka merge` for context nodes
- Correction flow (spec decision log #15)
- Dedicated validation LLM call
- Retrieval session memory
- Shorter CLI alias (e.g. `wl`) — add via extra entry point later; no arch change
- Per-provider prompt tuning

---

## Recommended order (updated)

1. **0.5–0.7** — finish M0 (config `data_dir` + first-run storage prompt)
3. **1.1–1.8** — records on disk (M1)
4. **S.1–S.3** — dependency spikes (gate)
5. **2.1–2.4** + **3.1–3.2** + **4.2** — indexes + rebuild (M2)
6. **5.1** + **6.6** + **6.12a** — mocked ingest path (M3)
7. **7.1–7.7a** — mocked retrieval (M5)
8. **8.x** + **9.x** + **6.12b / 7.7b** — REPL, polish, live smokes (M6)

---

## Working agreement

Pick one step number (e.g. `0.3b`). Implement only that step, verify, then proceed.
Mark completed steps with **✓** in this file.
