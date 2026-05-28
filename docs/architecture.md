# yanka architecture

This document explains how yanka is put together: the problem shape, the storage
model, the role of the LLM, and the runtime flows that tie them together. It is
grounded in what is actually implemented in v1 and cross-references the spec
([`yanka-spec.md`](../yanka-spec.md)) where useful.

If you want the user-facing tour, read [`../README.md`](../README.md) first.

---

## 1. What yanka is solving

Engineering decisions live in heads, Slack threads, and meeting notes — high
signal, low durability. Templates and forms don't get filled in; wiki pages go
stale. Yanka assumes the only input the user is willing to give is a brain
dump in natural language, and the only retrieval they will tolerate is asking
a question in natural language.

So the architecture has to do two things the user will not:

1. Turn a messy dump into a structured, supersedable record.
2. Turn a fuzzy question into a precise retrieval over those records.

Everything else — file layout, indexes, conflict detection, supersession
chains — exists to make those two operations cheap, correct, and recoverable.

---

## 2. The core architectural bet

Three commitments shape every other choice:

1. **Markdown files are the source of truth.** Records are human-readable
   markdown with YAML frontmatter. The user can `cat`, `git diff`, and edit
   them by hand. If yanka burns down, the user still has their decisions.
2. **Indexes are derived state.** The graph DB and vector DB are caches over
   the markdown. `yanka rebuild` reconstructs both from `records/` alone. This
   is the safety net and the migration path.
3. **The LLM is a bridge, not a brain.** Application code owns orchestration,
   validation, persistence, and conflict resolution. The LLM is called at
   specific, narrow points where the job is "turn natural language into
   structure" or "turn structure into natural language" — and nowhere else.

These three together give a system that is auditable (you can read the files),
recoverable (you can rebuild the indexes), and bounded (you can point at every
place the LLM influences state).

---

## 3. Component map

```
┌─────────────────────────────────────────────────────────────┐
│  User                                                       │
│  (terminal: types /log, /ask, /resume, /people, ...)         │
└────────────────────────┬────────────────────────────────────┘
                         │
            ┌────────────▼─────────────┐
            │  CLI / REPL              │   src/yanka/cli.py
            │  - dispatches commands   │   src/yanka/repl/
            │  - renders Rich output   │
            │  - maps errors to UX     │
            └────────────┬─────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
 ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
 │ Ingest       │ │ Retrieval    │ │ Rebuild /        │
 │ pipeline     │ │ pipeline     │ │ inspection       │
 │ (/log)       │ │ (/ask)       │ │ (/people, /proj, │
 │              │ │              │ │  /config, CLI    │
 │ ingest/      │ │ retrieval/   │ │  rebuild)        │
 └──────┬───────┘ └──────┬───────┘ └────────┬─────────┘
        │                │                  │
        └────────┬───────┴───────────┬──────┘
                 │                   │
       ┌─────────▼──────────┐  ┌─────▼─────────────┐
       │ LLM client         │  │ Embeddings        │
       │ (LiteLLM-backed,   │  │ (FastEmbed,       │
       │  typed errors,     │  │  all-MiniLM-L6)   │
       │  retry-once)       │  │                   │
       │ src/yanka/llm/     │  │ src/yanka/        │
       │                    │  │  embeddings*.py   │
       └─────────┬──────────┘  └─────────┬─────────┘
                 │                       │
                 ▼                       ▼
         external provider      (no external service)
         (Claude/OpenAI/...)

        ┌──────────────────────────────────────────┐
        │  Storage (local, embedded)               │
        │                                          │
        │  ┌────────────┐ ┌────────┐ ┌──────────┐  │
        │  │ Filesystem │ │ Graph  │ │ Vector   │  │
        │  │ records/   │ │ Ladybug│ │ Lance    │  │
        │  │ changelog  │ │ graph/ │ │ vectors/ │  │
        │  └────────────┘ └────────┘ └──────────┘  │
        │                                          │
        │  runtime/   - logs, pending sessions     │
        │  config.yaml - effective config          │
        └──────────────────────────────────────────┘
```

Everything runs in a single Python process. There are no servers, no daemons,
and no network dependencies other than the LLM provider call.

---

## 4. Storage layers, and why there are three

Three layers, three jobs. Each is the *only* thing that does its job well; the
others would do it badly or slowly.

### 4.1 Filesystem — source of truth

**Where:** `<data_dir>/records/YYYY-MM-DD-<slug>.md` plus the append-only
`<data_dir>/changelog.jsonl`.
**Code:** `src/yanka/records/` (parse/serialize/validate), `src/yanka/ingest/write.py`
(atomic write + changelog), `src/yanka/rebuild.py` (re-derive indexes).

What it stores: every record, in full, as a markdown file with YAML
frontmatter. The frontmatter carries structured fields (`date`, `type`,
`status`, `context_path`, `people`, `tags`, `claims[]`, optional
`supersedes`). The body holds the human-written sections (rationale,
alternatives, implications, raw input, etc.).

Why it exists and why it's first:

- **Durability**: text files survive any other component dying. The user can
  read, grep, edit, and version-control them without yanka running.
- **Auditability**: `changelog.jsonl` is an append-only record of every
  create/supersede operation, with hashes. You can replay history.
- **Recoverability**: see §7. The graph and vector layers are reconstructed
  from these files. If markdown is intact, the system is intact.

What it deliberately does **not** do: it cannot answer "which decisions are
about auth?" without re-reading every file. That's what the indexes are for.

### 4.2 Graph DB — structural relationships (LadybugDB)

**Where:** `<data_dir>/graph/` (embedded, in-process, Cypher).
**Code:** `src/yanka/graph/` — schema, indexing on write, context/alias
resolution, retrieval, and inspection.

What it stores (spec §4): nodes for `Context`, `Decision`, `Claim`, `Person`,
and edges `contains`, `about`, `has_claim`, `supersedes`, `involves`. It holds
**references to records, not record content**. The full text still lives in
markdown.

Why a graph specifically:

- Decisions form **hierarchies** (`main-platform → auth-service →
  token-management`). A graph models that cleanly with `contains` edges and
  lets retrieval walk a subtree in one query.
- Claims **supersede** other claims, sometimes across records. Walking the
  supersession chain in a relational store would be a recursive CTE; in a
  graph it is one traversal.
- A question like "what has Carlos decided in the auth area in the last 90
  days?" is a multi-hop join (`Person → involves → Decision → about →
  Context`). Graphs are built for that.

Without the graph layer, every supersession check, every context lookup, and
every "show all decisions under X" query would either scan all files or
require us to invent the same data structure on top of SQL.

### 4.3 Vector DB — semantic search (LanceDB)

**Where:** `<data_dir>/vectors/` (embedded, in-process, columnar Lance).
**Code:** `src/yanka/vectors/` — schema, indexing, similarity search, metadata
filters. Embeddings come from `src/yanka/embeddings*.py` (FastEmbed + ONNX,
no PyTorch).

What it stores (spec §5): two tables.

- `records` table: one row per markdown file. Holds the embedding of the full
  record text plus denormalized metadata (`date`, `project`, `context_path`,
  `status`, `type`, `tags`, `summary`) for cheap filtering at query time.
- `claims` table: one row per claim. Holds the embedding of the claim's
  content plus parent metadata. Primary key is `<filename>:<claim_id>` so a
  claim can be uniquely addressed across the whole corpus.

Why vectors:

- The user does not know the exact wording of past decisions. They ask "are
  we still on Redis for sessions?" and need to land on a record that talks
  about "session store" or "in-memory cache". Keyword search and Cypher
  cannot do that; embeddings can.
- During ingest, vector search is also how we find **conflict candidates** —
  semantically near claims that might contradict a new one.

Without the vector layer, retrieval would be a glorified `grep`, and conflict
detection would only catch verbatim restatements.

### 4.4 How the three layers cooperate

| Question                                              | Layer used                       |
|-------------------------------------------------------|----------------------------------|
| "Give me the canonical text of this decision."        | Filesystem (markdown)            |
| "Did anything supersede this claim?"                  | Graph (`supersedes` traversal)   |
| "What decisions exist under `auth-service`?"          | Graph (subtree walk)             |
| "Anything semantically like this new claim?"          | Vector (similarity search)       |
| "Active claims under this context, fuzzy-matched."    | Vector + graph filter (merge)    |
| "Restore everything from scratch."                    | Filesystem → rebuild graph + vec |

Retrieval (`/ask`) explicitly combines graph and vector signals: the graph
contributes a structural skeleton and supersession-aware filtering, the
vector index contributes semantic discovery and the metadata for ranking.

---

## 5. Why LLMs are used (and where they are not)

The LLM is a bridge between unstructured language and structured data. We use
it only at the points where that bridging is what is needed — never as the
authority on what is true.

### 5.1 Where the LLM is used in ingest

Implemented across `src/yanka/ingest/` (`extraction.py`, `claims.py`,
`claim_validation.py`, `entity_resolution.py`, `conflict_evaluation.py`).

1. **Conversational extraction.** Take a free-form dump and produce a
   structured record with a `decision`, `context_path`, `people`, etc. This
   is iterative: the LLM asks clarifying questions until it can emit a record
   with `record_complete: true` and valid YAML, or hits `max_rounds` and is
   forced to wrap up. *Why an LLM:* this is exactly the natural-language →
   schema bridge nothing else does well.
2. **Claim extraction.** Decompose the finished record into 2–7 atomic,
   independently-supersedable claims. *Why an LLM:* "atomic, factual,
   independently changeable" is a judgement that needs language understanding.
3. **Claim validation (optional second LLM pass).** Lightweight coverage
   check: does any claim reflect the `decision` field? App code runs the
   keyword/embedding heuristic; an LLM retry is invoked only when the
   heuristic flags a gap. *Why an LLM:* paraphrase detection on short text.
4. **Entity resolution (LLM as fallback).** Most context paths resolve via
   the alias registry (pure app code). The LLM is asked only when an
   incoming label doesn't match any known canonical context node, and the
   question is "is this a new name for one of these existing nodes, or
   genuinely new?". *Why an LLM:* synonym/abbreviation matching is what it's
   good at; the result is cached as an alias so the same call is not repeated.
5. **Conflict evaluation.** Given a set of new claims and a candidate set of
   existing claims (from vector + graph), classify which pairs are actual
   conflicts. *Why an LLM:* contradiction detection needs semantics, not
   string similarity. Output is constrained JSON.

### 5.2 Where the LLM is used in retrieval

Implemented in `src/yanka/retrieval/query_analysis.py` and `synthesis.py`.

1. **Query analysis.** Take the user's natural question and emit a structured
   plan: `query_type` (current state / historical / specific / exploratory /
   relationship / person), metadata filters, a clean semantic query string, a
   graph hint. *Why an LLM:* same bridge in the other direction — intent
   extraction.
2. **Synthesis.** Take the merged record set produced by graph + vector
   retrieval and produce a cited answer in prose. *Why an LLM:* turning a
   ranked set of records into a readable answer with citations is exactly
   what generative models are for.

### 5.3 Where the LLM is **not** used (deliberately)

- Writing files. Persistence is app code.
- Updating the graph and vector indexes. App code.
- Computing supersession edges. App code, driven by user confirmation of
  detected conflicts.
- Deciding what's true on conflict. App code presents conflicts; the **user**
  resolves them.
- Statusline, /people, /projects, /config, /help. Pure app code.
- Rebuild. Pure app code reading markdown.

LLM calls are isolated behind `src/yanka/llm/client.py`, which standardises
typed errors (`LlmAuthError`, `LlmRateLimitError`, `LlmTimeoutError`,
`LlmTransportError`) and applies one retry for transient failures. Every
caller assumes the LLM can fail and degrades accordingly (see §8).

---

## 6. Runtime flows

### 6.1 CLI / REPL bootstrap

Entry point: `src/yanka/cli.py`.

1. Resolve data paths (`resolve_data_paths` in `src/yanka/paths.py`).
   Precedence: explicit `--data-dir` → `config.yaml` → `$YANKA_DATA_DIR` →
   `~/.yanka`.
2. If `config.yaml` is missing, run first-run setup (`src/yanka/setup.py`):
   pick an LLM provider, store the API key in the OS keychain via
   `src/yanka/secrets.py` (env var fallback).
3. Configure rotating file logging at `<data_dir>/runtime/yanka.log`
   (`src/yanka/app_logging.py`).
4. Either run the named subcommand (`rebuild`, etc.) or enter the REPL
   (`src/yanka/repl/loop.py`).

### 6.2 Ingest flow (`/log`)

Orchestrator: `run_ingest_pipeline` in `src/yanka/ingest/pipeline.py`. Stages
emit `IngestActivityStage` events so the REPL spinner reflects real progress.

| # | Stage           | Owner    | Storage touched     |
|---|-----------------|----------|---------------------|
| 1 | `searching`     | app code | vectors (read)      |
| 2 | `extracting`    | LLM loop | (none — in memory)  |
| 3 | claim extract   | LLM      | (none — in memory)  |
| 4 | `validating`    | app code + optional LLM | (none) |
| 5 | entity resolve  | app code + optional LLM | graph (read+aliases) |
| 6 | conflict search | app code | vectors + graph (read) |
| 7 | `conflict-check`| LLM      | (none — in memory)  |
| 8 | confirmation    | app + user | (none)            |
| 9 | `writing`       | app code | filesystem → changelog → graph → vectors |
| 10| display result  | app code | (none)              |

Write ordering in step 9 is deliberate and matters:

1. Markdown file is written first. It is the source of truth.
2. Changelog line is appended.
3. Graph nodes/edges are upserted with parameterized Cypher
   (`src/yanka/graph/indexing.py`), including supersession edges for any
   claims the user confirmed as conflicts.
4. Embeddings are computed and inserted into the vector tables.

If step 3 or 4 fails, the markdown is still there and is logged as the
ingoing point for the next `yanka rebuild`. Index failures are warnings, not
fatal errors.

**Resume**: if an LLM error occurs *after* extraction succeeded (steps 5–9),
the pipeline raises `IngestAbortError` carrying the stage and the in-memory
record. The REPL persists this to `<data_dir>/runtime/pending_log_session.json`
and `/resume` can replay from the saved stage. No partial state is written to
graph or vectors.

### 6.3 Retrieval flow (`/ask`)

Orchestrator: `run_retrieval_pipeline` in `src/yanka/retrieval/pipeline.py`.

| # | Stage           | Owner    | Storage touched              |
|---|-----------------|----------|------------------------------|
| 1 | `analyzing`     | LLM      | (none — in memory)           |
| 2 | `graph`         | app code | graph (read)                 |
| 2 | `vectors`       | app code | vectors (read)               |
| 3 | merge           | app code | (in memory)                  |
| 4 | `synthesizing`  | LLM      | filesystem (read of cited records) |
| 5 | output          | app code | (none)                       |

The merge step is where the graph and vector worlds reconcile (spec §8): graph
hits are the skeleton, joint hits get higher confidence, vector-only hits are
treated as discovery, and anything the graph knows is superseded is dropped.

**Stale-index resilience.** If the merged result set references a markdown
file that no longer exists on disk (graph/vector got out of sync with the
filesystem), `src/yanka/retrieval/synthesis.py` skips the missing file,
continues with what's available, and the `RetrievalResult.warnings` field
carries a `STALE_INDEX_WARNING` telling the user to run `/rebuild`. If
*everything* is stale, the pipeline returns a clean fallback answer instead
of crashing.

### 6.4 Rebuild flow

Entry point: `yanka rebuild` (`src/yanka/rebuild.py`). Reads every markdown
file from `records/`, rebuilds graph nodes/edges and re-embeds into the
vector store. This is the round-trip proof that the filesystem is in fact
the source of truth.

---

## 7. Cross-cutting concerns

### 7.1 Recovery guarantees

- Markdown files are written before any index update.
- The changelog is append-only and content-hashed.
- Graph and vector directories are disposable: deleting them and running
  `yanka rebuild` reproduces them.
- A stale or partially-indexed corpus does not break retrieval (see §6.3);
  it surfaces a warning.

### 7.2 Error model

Defined in `src/yanka/llm/client.py` and `src/yanka/repl/errors.py`.

- LLM errors are typed: `LlmAuthError`, `LlmRateLimitError`,
  `LlmTimeoutError`, `LlmTransportError`. The client applies one retry to
  transport-like transient failures.
- REPL command handlers (`src/yanka/repl/commands/`) catch these, log full
  context to `yanka.log` via `src/yanka/app_logging.py`, render a short
  user-facing message, and never bubble raw tracebacks to the terminal.
- `IngestAbortError` carries enough state to seed a `/resume`.

### 7.3 Logging

Configured by `src/yanka/app_logging.py`:

- File: `<data_dir>/runtime/yanka.log`.
- Rotation: 5 MB per file, 3 backups, total bounded at ~20 MB.
- Records exception tracebacks and structured per-command context.
- Terminal output stays minimal; full diagnostics live in the log.

### 7.4 Configuration and secrets

- Effective config is read from `<data_dir>/config.yaml` (see spec §6) by
  `src/yanka/config.py`. The `/config` REPL command renders the effective
  values for inspection.
- API keys are *never* in `config.yaml`. They live in the OS keychain
  (`keyring`), with environment variables as a fallback. Handled by
  `src/yanka/secrets.py`.

### 7.5 REPL UX

- `src/yanka/repl/loop.py` runs the prompt loop and routes commands.
- `src/yanka/repl/statusline_cache.py` caches the record count so the
  prompt does not re-scan the records directory on every keystroke; the
  cache is invalidated when ingest writes a new record.
- Pipeline stages emit `IngestActivityStage` / `RetrievalActivityStage`
  events (`src/yanka/ui/pipeline_activity.py`) to drive a real-progress
  spinner instead of a generic "thinking…".
- Inspection commands (`/people`, `/projects`, `/config`, `/help <topic>`)
  query the graph and config directly; no LLM is involved.

---

## 8. Module map

| Concern                          | Path                                          |
|----------------------------------|-----------------------------------------------|
| CLI entry                        | `src/yanka/cli.py`                            |
| First-run setup                  | `src/yanka/setup.py`                          |
| Config                           | `src/yanka/config.py`                         |
| Paths layout                     | `src/yanka/paths.py`                          |
| Secrets / keychain               | `src/yanka/secrets.py`                        |
| Logging                          | `src/yanka/app_logging.py`                    |
| LLM client + typed errors        | `src/yanka/llm/`                              |
| Embeddings                       | `src/yanka/embeddings.py`, `embeddings_fastembed.py` |
| Records (parse/serialize/write)  | `src/yanka/records/`, `src/yanka/ingest/write.py`    |
| Ingest pipeline                  | `src/yanka/ingest/`                           |
| Retrieval pipeline               | `src/yanka/retrieval/`                        |
| Graph store                      | `src/yanka/graph/`                            |
| Vector store                     | `src/yanka/vectors/`                          |
| Rebuild                          | `src/yanka/rebuild.py`                        |
| REPL loop + commands             | `src/yanka/repl/`                             |
| UI rendering                     | `src/yanka/ui/`                               |

---

## 9. Test strategy

- **Unit tests** under `tests/` cover records, graph, vectors, LLM client,
  REPL command handlers, and individual pipeline stages.
- **Pipeline tests** validate `run_ingest_pipeline` and `run_retrieval_pipeline`
  with mocked LLM hooks and real embedded graph/vector stores.
- **Integration tests** under `tests/integration/` cover end-to-end scenarios
  with real local stores and a mocked LLM: happy-path ingest, conflict
  supersession, retrieval happy path, stale-index recovery, `/resume` after
  extraction error, post-write index failure, and `/rebuild` recovery.

Together they validate the architectural invariants documented above:
markdown is canonical, indexes are derived, LLM failures degrade gracefully,
and rebuild is the universal escape hatch.
