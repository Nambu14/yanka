# Yanka — Complete Project Specification

> This is the single source of truth for building Yanka.
> Every design decision, schema, prompt, and UX behavior is documented here.
> Nothing should be built that contradicts this document.

---

## Table of contents

1. [Overview](#overview)
2. [Storage architecture](#storage-architecture)
3. [Record template](#record-template)
4. [Graph schema (LadybugDB)](#graph-schema)
5. [Vector schema (LanceDB)](#vector-schema)
6. [Config format](#config-format)
7. [Ingest pipeline](#ingest-pipeline)
8. [Retrieval pipeline](#retrieval-pipeline)
9. [Entity resolution](#entity-resolution)
10. [Prompts](#prompts)
11. [CLI UX](#cli-ux)
12. [Error handling](#error-handling)
13. [Dependencies](#dependencies)
14. [Decision log](#decision-log)
15. [Open questions](#open-questions)

---

<a id="overview"></a>
## 1. Overview

Yanka is a CLI tool that captures engineering decisions through natural conversation and makes them retrievable through natural language queries. The user talks, the system structures, stores, and indexes. No templates, no forms, no manual organization.

**Core principle:** The unit of input is a conversation. The unit of storage is a structured record. The user never interacts with the structure directly — the LLM bridges the gap in both directions.

**Distribution:** Python CLI, pip-installable. Rich terminal output via the `rich` library. Cloud version deferred until CLI is validated.

---

<a id="storage-architecture"></a>
## 2. Storage architecture

Three layers: filesystem (source of truth) + graph DB (structural relationships) + vector DB (semantic search).

### Filesystem (source of truth)

Markdown files with YAML frontmatter. One file per decision record. Plus an append-only changelog for audit trail.

```
~/.yanka/
├── records/                # Markdown decision records
│   └── YYYY-MM-DD-<slug>.md
├── changelog.jsonl         # Append-only operation log
├── graph/                  # LadybugDB files (disposable, rebuildable)
├── vectors/                # LanceDB files (disposable, rebuildable)
├── runtime/                # App logs + interrupted session state
│   ├── yanka.log           # Bounded rotating log (see §12)
│   └── pending_log_session.json  # Resume payload (see §7, §12)
└── config.yaml             # User configuration
```

`runtime/` is disposable: deleting it loses recent log history and any
unfinished `/log` session, but no committed record data. It is never read
by `yanka rebuild`.

**Changelog format:** One JSON line per operation.
```json
{"ts": "2026-05-14T10:23:00Z", "action": "create", "file": "2026-05-14-jwt-auth-approach.md", "hash": "a3f2..."}
{"ts": "2026-05-14T14:01:00Z", "action": "supersede", "file": "2026-05-14-drop-redis-sessions.md", "supersedes_file": "2026-03-02-redis-session-store.md", "supersedes_claims": [{"new": "c1", "old": "2026-03-02-redis-session-store.md:c1"}], "hash": "b7c1..."}
```

**Rebuild guarantee:** `graph/` and `vectors/` are fully disposable. `yanka rebuild` reconstructs both entirely from the markdown files. This is the recovery mechanism, migration path, and proof that the filesystem is the true source of truth.

### Graph DB — LadybugDB

Embedded, serverless, in-process. Cypher query language. Python SDK via pip.

Holds structural relationships only — references back to filesystem records, does not hold full content.

### Vector DB — LanceDB

Embedded, serverless, in-process. Lance columnar format. Supports vector + full-text + SQL filtering in a single query. Python SDK via pip.

Holds embeddings of record text and claims, with metadata for filtering.

### Embedding model

FastEmbed with all-MiniLM-L6-v2. ONNX runtime, no PyTorch, ~150-200MB install. Runs on CPU, millisecond inference.

Behind a single-function abstraction:
```python
def embed(texts: list[str]) -> list[list[float]]:
```

Swappable via config. Changing model requires `yanka rebuild` to re-embed everything.

---

<a id="record-template"></a>
## 3. Record template

Every decision record is a markdown file with this exact structure:

```yaml
---
date: 2026-05-14
type: decision
status: active
record_complete: true   # Required completion signal — set only on final record output

# Graph structure
context_path: [main-platform, auth-service, token-management]
people: [Carlos, Jamie]
supersedes: null

# Searchability
tags: [infrastructure, redis, session-management]
decision: "Drop Redis for session storage, move to direct DB storage"

# Extracted claims (independently supersedable)
claims:
  - id: c1
    content: "Session data is stored directly in PostgreSQL"
    status: active
  - id: c2
    content: "Redis is no longer used for session storage"
    status: active
  - id: c3
    content: "Session read latency target is under 50ms"
    status: tentative
    supersedes: {file: 2026-02-10-redis-session-store.md, claim: c1}
---

## Rationale
Why this was chosen. What constraints drove the decision.

## Alternatives considered
- Alternative A (rejected: reason)
- Alternative B (rejected: reason)
If none discussed, state why (obvious choice, time pressure, mandate).

## Scope and boundaries
What this covers. What it explicitly does NOT cover.

## Implications
What changes downstream. What other decisions this forces or enables.

## Open questions
Unresolved points. Revisit triggers with specifics — thresholds, dates, conditions.

## Ownership
Who is carrying this forward. Who to ask about it.

## Context snapshot
Environmental factors — team size, system scale, version numbers, temporary constraints. Only if relevant.

## Raw input
> The user's original dump, verbatim. Always include. Never edit.
```

### Field definitions

- **date:** YYYY-MM-DD. Today's date unless user mentions a different one.
- **type:** One of: `decision`, `meeting-summary`, `discovery`, `context`, `problem-statement`.
- **status:** `active` (default), `tentative` (user signals uncertainty), `superseded` (system-set when replaced).
- **context_path:** Ordered list representing the hierarchy. First element = project, subsequent = increasingly specific. Short, lowercase, hyphenated slugs.
- **people:** Names of participants or decision-makers. Not people mentioned in passing.
- **supersedes:** Null in initial extraction. Set by the system during conflict detection.
- **tags:** 2-5 freeform cross-cutting concerns.
- **decision:** 1-2 sentence core takeaway.
- **record_complete:** Must be `true` on the final record the LLM produces. Application code treats a record as complete only when this field is present **and** frontmatter parses as valid YAML with all required keys (`date`, `type`, `status`, `context_path`, `decision`). A bare `---` marker alone is not sufficient — prevents false positives from incidental markdown.
- **claims:** Array of atomic, independently supersedable assertions. Each has `id` (c1, c2...), `content`, `status`, and optionally `supersedes` linking to a specific claim in another file. Populated after extraction (claim prompt), not by the extraction prompt.

### Body sections

Include only sections with meaningful content. Omit empty ones rather than writing "N/A".

---

<a id="graph-schema"></a>
## 4. Graph schema (LadybugDB)

### Node types

**Context**
- `canonical_name` (string)
- `aliases` (list of strings)
- `normalized_name` (string, **indexed** — lowercase/stripped for fast matching)
- `depth` (int — 0 for project, 1 for subsystem, etc.)

**Decision**
- `file_reference` (string — filename, **indexed**)
- `date` (date, **indexed**)
- `type` (string)
- `status` (string — active/tentative/superseded)
- `summary` (string — 1-2 sentence takeaway)
- `tags` (list of strings)

**Claim**
- `claim_id` (string — c1, c2, etc.)
- `content` (string — the assertion text)
- `status` (string — active/tentative/superseded)
- `source_file` (string — which record it came from)

**Person**
- `name` (string, **indexed**)
- `aliases` (list of strings)

### Edge types

- **contains** — context → context (builds hierarchy)
- **about** — decision → context (anchors decision to hierarchy)
- **has_claim** — decision → claim
- **supersedes** — claim → claim (within same context, carries source_file on both ends)
- **involves** — decision → person

### Indexes

- `Context.normalized_name` — entry point for entity resolution
- `Decision.file_reference` — link from filesystem to graph
- `Decision.date` — temporal queries
- `Person.name` — person lookups

---

<a id="vector-schema"></a>
## 5. Vector schema (LanceDB)

### Records table

| Column | Type | Purpose |
|---|---|---|
| file_reference | string (primary key) | Links to filesystem |
| vector | float[384] | Embedding of full record text |
| date | date | Temporal filtering |
| context_path | string | Joined path for prefix filtering (e.g., "main-platform/auth-service/token-management") |
| project | string | First element of context_path for fast project-level filtering |
| status | string | active/tentative/superseded |
| type | string | decision/meeting-summary/discovery/context/problem-statement |
| tags | list[string] | Tag filtering |
| summary | string | Display text without reading file |

### Claims table

| Column | Type | Purpose |
|---|---|---|
| claim_id | string (primary key) | Composite: "filename:c1" for global uniqueness |
| vector | float[384] | Embedding of claim content |
| content | string | The assertion text |
| status | string | active/superseded/tentative |
| source_file | string | Links to parent record |
| date | date | Inherited from parent record |
| context_path | string | Inherited from parent record |
| project | string | Inherited from parent record |

Metadata is denormalized from records into claims — single query can filter claims by project + status + date without joins.

---

<a id="config-format"></a>
## 6. Config format

Stored at `~/.yanka/config.yaml`:

```yaml
llm:
  provider: claude          # claude | openai | google | ollama
  model: claude-sonnet-4-20250514  # provider-specific model string
  endpoint: null            # custom endpoint for ollama

embedding:
  provider: local                          # local | openai | voyage
  model: sentence-transformers/all-MiniLM-L6-v2

extraction:
  max_rounds: 2             # max clarifying rounds before forced wrap-up
  conflict_search_limit: 10 # max candidates from vector + graph search for conflict detection
  context_search_limit: 5   # max related records injected into extraction prompt context

data_dir: ~/.yanka
```

**Extraction defaults rationale:** `max_rounds: 2` keeps the clarifying loop
tight by default — most dumps are good enough after one round of questions,
and the wrap-up prompt produces a record at the cap. Users who want longer
back-and-forth can raise it. `context_search_limit: 5` bounds how many
semantic neighbours are pulled into the extraction prompt (Step 1 of §7) so
the prompt stays small and the LLM stays focused.

**API keys:** Never stored in config file. Stored in system keychain via Python `keyring` library (macOS Keychain, Linux Secret Service, Windows Credential Manager). Environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.) as fallback. Keychain takes precedence.

**First-run flow:** Only asks `llm.provider` and API key. Everything else uses defaults.

**LLM abstraction:** LiteLLM for provider switching. Supports Claude, OpenAI, Google, Ollama.

---

<a id="ingest-pipeline"></a>
## 7. Ingest pipeline

**Orchestration model:** Application code is the orchestrator. LLM is called at specific defined points. No agent frameworks.

```
User sends /log + raw dump
        │
        ▼
┌─────────────────────────┐
│  Step 1: Context search  │  Embed the raw dump, search LanceDB
│  (app code)              │  for related existing records. Inject
│                          │  into LLM context. These are rough
│                          │  matches — the LLM is told to treat
│                          │  them with a grain of salt.
└───────────┬──────────────┘
            │
            ▼
┌─────────────────────────┐
│  Step 2: Conversational  │  While loop. LLM asks clarifying
│  extraction              │  questions about knowledge gaps.
│  (LLM — extraction       │  User answers. Loop until LLM produces
│   prompt)                │  valid record (record_complete: true
│                          │  + required frontmatter keys) or
│                          │  max_rounds cap triggers wrap-up.
└───────────┬──────────────┘
            │
            ▼
┌─────────────────────────┐
│  Step 3: Claim           │  Separate LLM call. Takes the finished
│  extraction              │  record, returns JSON array of atomic
│  (LLM — claim prompt)   │  claims. 2-7 claims per record.
└───────────┬──────────────┘
            │
            ▼
┌─────────────────────────┐
│  Step 4: Claim           │  Lightweight check that claims cover
│  validation              │  the record's decision field. Retry
│  (app code + optional    │  claim extraction once if gaps found.
│   LLM — validation       │  See "Claim validation" below.
│   prompt)                │
└───────────┬──────────────┘
            │
            ▼
┌─────────────────────────┐
│  Step 5: Entity          │  Resolve context_path from the record
│  resolution              │  to graph nodes using alias registry.
│  (app code + LLM         │  Normalize → check aliases → LLM
│   fallback)              │  fallback for unknowns → ask user
│                          │  for ambiguous cases.
└───────────┬──────────────┘
            │
            ▼
┌─────────────────────────┐
│  Step 6: Conflict        │  Two parallel candidate sources:
│  search                  │  (1) Vector — embed each new claim,
│  (app code)              │  search LanceDB for semantic neighbors.
│                          │  (2) Graph — all active claims under
│                          │  the resolved context subtree. Merge,
│                          │  dedupe by claim_id. Max candidates
│                          │  from config applies to merged set.
└───────────┬──────────────┘
            │
            ▼
┌─────────────────────────┐
│  Step 7: Conflict        │  "Here are new claims and candidate
│  evaluation              │  existing claims. Which are actual
│  (LLM — conflict prompt) │  conflicts?" Structured JSON output.
│                          │  Skipped if no candidates found.
└───────────┬──────────────┘
            │
            ▼
┌─────────────────────────┐
│  Step 8: User            │  Surface real conflicts naturally:
│  confirmation            │  "Didn't we already decide X?"
│  (app code)              │  User confirms or denies each.
│                          │  Skipped if no conflicts detected.
└───────────┬──────────────┘
            │
            ▼
┌─────────────────────────┐
│  Step 9: Write to        │  1. Write markdown file to records/
│  stores                  │  2. Append to changelog.jsonl
│  (app code)              │  3. Create graph nodes/edges
│                          │  4. Mark superseded claims inactive
│                          │  5. Embed and insert into LanceDB
│                          │  File always written FIRST (source
│                          │  of truth). Graph/vector can be
│                          │  rebuilt if they fail (warning, not
│                          │  fatal). LLM failures between Step 2
│                          │  and Step 9 raise IngestAbortError
│                          │  carrying the stage + in-memory
│                          │  record; the REPL persists it to
│                          │  runtime/pending_log_session.json
│                          │  for stage-aware `/resume`.
└───────────┬──────────────┘
            │
            ▼
┌─────────────────────────┐
│  Step 10: Confirmation   │  Show: context path, decision summary,
│  (app code)              │  claims, superseded records, tags,
│                          │  filename. Rich terminal formatting.
└─────────────────────────┘
```

### Conversational extraction loop (Step 2 detail)

```python
REQUIRED_FRONTMATTER_KEYS = ("date", "type", "status", "context_path", "decision", "record_complete")

def is_complete_record(response: str) -> bool:
    frontmatter = parse_yaml_frontmatter(response)  # strict YAML parse
    if frontmatter is None:
        return False
    if frontmatter.get("record_complete") is not True:
        return False
    return all(k in frontmatter for k in REQUIRED_FRONTMATTER_KEYS)

conversation = [system_prompt + existing_records, user_dump]

while rounds < max_rounds:
    response = llm.complete(conversation)
    conversation.append(response)

    if is_complete_record(response):
        break  # LLM produced final record

    # It's clarifying questions — show to user
    user_reply = prompt_user(response)
    conversation.append(user_reply)
    rounds += 1

if rounds >= max_rounds and not is_complete_record(conversation[-1]):
    # Force wrap-up
    conversation.append("Please produce the record now with what you have. Mark unknowns as [not discussed]. Set record_complete: true in frontmatter.")
    response = llm.complete(conversation)

return parse_record(response)  # strips record_complete before persisting if desired, or keep it
```

**Completion signal:** `record_complete: true` in YAML frontmatter plus valid required keys. Application code never treats bare `---` or partial frontmatter as completion.

### Claim validation (Step 4 detail)

Catches drift between the extraction pass (record + `decision` field) and the claim extraction pass.

1. **App code (always):** Claims array is non-empty. Each claim has `id`, `content`, `status`.
2. **App code (coverage heuristic):** The `decision` field's core assertion is reflected in at least one claim's `content` (keyword overlap or simple embedding similarity — implementation choice).
3. **If coverage fails:** One retry of claim extraction (Prompt 2) with the `decision` field and any missed body sections appended as explicit input ("ensure claims cover: …").
4. **If still failing after retry:** Proceed with claims as-is; flag in confirmation output (amber) that claim coverage may be incomplete. Never block the write.

Optional future tightening: a dedicated validation LLM call. Not required for v1.

### Graph-assisted conflict search (Step 6 detail)

Runs after entity resolution so `context_path` maps to resolved graph nodes.

**Vector candidates:** Embed each new claim → LanceDB claims table → filter by project, context prefix, `status=active` → top-K by similarity.

**Graph candidates:** From the deepest resolved context node, traverse the context subtree (`contains` edges), find all `Decision` nodes with `about` edges into that subtree, follow `has_claim` to `Claim` nodes where `status=active`. Returns structurally related claims even when wording differs (catches renames, negation, scope-local reversals that embeddings miss).

**Merge:** Union both candidate sets, dedupe by `claim_id` (filename:cN). Apply `conflict_search_limit` to the merged list (prioritize graph hits that share exact context leaf, then highest vector similarity).

---

<a id="retrieval-pipeline"></a>
## 8. Retrieval pipeline

```
User sends /ask + question
        │
        ▼
┌─────────────────────────┐
│  Step 1: Query analysis  │  Classify query type, extract filters,
│  (LLM — query prompt)   │  produce semantic query and graph hint.
│                          │  Structured JSON output.
└───────────┬──────────────┘
            │
            ▼
┌──────────────────────────────────────┐
│  Step 2: Parallel retrieval          │
│  (app code)                          │
│                                      │
│  ┌─────────────┐  ┌───────────────┐  │
│  │ Graph query  │  │ Vector search │  │
│  │ (LadybugDB) │  │ (LanceDB)    │  │
│  │              │  │              │  │
│  │ Cypher query │  │ Embed        │  │
│  │ pattern      │  │ semantic     │  │
│  │ selected by  │  │ query,       │  │
│  │ query_type + │  │ apply        │  │
│  │ graph_hint.  │  │ metadata     │  │
│  │              │  │ filters.     │  │
│  └──────┬──────┘  └──────┬────────┘  │
│         └───────┬────────┘           │
│                 ▼                    │
│  Step 3: Graph-anchored merge        │
│                                      │
│  - Graph results = skeleton          │
│  - Both graph + vector = higher      │
│    confidence                        │
│  - Vector-only = discovery           │
│    (enrichment)                      │
│  - Remove superseded records that    │
│    vector surfaced but graph knows   │
│    are inactive                      │
└───────────┬──────────────────────────┘
            │
            ▼
┌─────────────────────────┐
│  Step 4: Synthesis       │  "Based on these records, answer the
│  (LLM — synthesis        │  question. Cite sources. Flag if
│   prompt)                │  outdated or low confidence."
│                          │  Plain text output. Stale-index
│                          │  resilience: merged hits that point
│                          │  to missing markdown files are
│                          │  skipped; a STALE_INDEX_WARNING is
│                          │  attached to the result with a
│                          │  `/rebuild` suggestion. If every hit
│                          │  is stale, a clean fallback answer
│                          │  is returned instead of crashing.
└───────────┬──────────────┘
            │
            ▼
┌─────────────────────────┐
│  Step 5: Output          │  Formatted answer with citations,
│  (app code)              │  supersession timeline if applicable,
│                          │  source list with status badges,
│                          │  staleness warnings. Rich formatting.
└─────────────────────────┘
```

### Query types (from query analysis)

| Type | Graph behavior | Vector behavior |
|---|---|---|
| current_state | Find active decisions for context node | Filter to status=active |
| historical | Walk full supersession chain | Return all statuses |
| specific_decision | Find by file reference or summary match | Semantic search on decision details |
| exploratory | Broad traversal of matching context area | Broad semantic search |
| relationship | Traverse downstream/upstream edges from target | Find semantically related records |
| person | Follow involves edges from person node | Skip or supplement |

### Retrieval sessions

Independent in v1. No session continuity between /ask queries. Each query is self-contained. Session management deferred to v2.

---

<a id="entity-resolution"></a>
## 9. Entity resolution

Alias registry system for matching user's natural language to graph context nodes.

### Flow

1. LLM extracts `context_path` from the dump: `[project, subsystem, component]`
2. For each level, application code normalizes: lowercase, strip common suffixes ("service", "system", "module")
3. Check existing aliases → direct match → resolved
4. No match → pull existing nodes at that level, send to LLM: "Does 'login service' refer to one of these, or is it new?"
5. LLM maps to existing → add new phrasing to alias list → resolved
6. LLM says new → create node
7. LLM uncertain → ask user as a natural clarifying question
8. Resolution is permanent — alias stored, never needs resolving again for same phrasing

### Context node properties

```
canonical_name: "authentication-service"
aliases: ["auth service", "auth", "login service", "authentication"]
normalized_name: "authentication"
```

### Characteristics

- First month is LLM-call-heavy as alias lists build up
- Increasingly cached over time — most phrasings get resolved for free
- 4k nodes is the upper bound for a heavy user — fits in memory, fits in a prompt
- Future: `yanka merge <node-a> <node-b>` to combine nodes (not v1)

---

<a id="prompts"></a>
## 10. Prompts

Five distinct prompts, each with a specific job, input, and output contract.

---

### Prompt 1: Extraction

**When:** Step 2 of ingest pipeline (conversational loop).
**Input:** System prompt + related existing records (from context search) + user dump + ongoing conversation history.
**Output:** Structured record with YAML frontmatter including `record_complete: true`. Application code validates required keys — do not rely on `---` alone.
**NOT output:** Claims block (that's prompt 2). Supersession (that's the system's job).

**System prompt:**

```
You are a technical decision recorder. Your job is to turn unstructured brain dumps — meeting recaps, technical decisions, things learned, context worth preserving — into complete, well-structured decision records.

You are not a form. You are a sharp senior engineer who listens, infers what you can, and then asks the questions that future-someone will wish had been asked today.

CONTEXT YOU RECEIVE:
1. The user's raw dump.
2. Existing records (possibly). These are rough semantic matches pulled from the knowledge base. Some may be relevant, some may be noise. Use them if they help you ask better questions or spot connections. Ignore them if they don't connect. Never mention to the user that you received these.

HOW A SESSION WORKS:
1. User dumps raw input.
2. Silently analyze and mentally fill the record template. Do NOT show the template.
3. Identify knowledge gaps — not missing fields, but places where the record would be ambiguous to someone reading it in 6 months.
4. If existing records suggest a connection, factor that into your questions naturally.
5. Ask about gaps in batched questions — one message, 2-4 related questions. Never one per message.
6. Multiple rounds are fine. Stop when a future reader would have clear understanding.
7. Produce the final structured record.

WHAT TO ASK ABOUT (knowledge gaps):
- Unstated constraints and rejection reasons
- Scope and boundaries
- Implications and downstream effects
- Confidence level and revisit triggers (specific thresholds, not "if needed")
- Ownership and next steps
- "Obvious" context that won't be obvious later (versions, scale, team composition)
- Connections to existing records (only if genuinely relevant)

WHAT NOT TO ASK ABOUT:
- Template metadata you can infer (topic, tags, type, date)
- Things they already said
- Field-by-field confirmation
- Low-value metadata (tags, status unless ambiguous)
- Context path placement (infer from dump)

QUESTION STRATEGY:
- Batch related questions, 2-4 per message
- Lead with the most important gap
- Be specific, not generic
- Use their language and names
- Stop at diminishing returns (3-4 rounds)
- Match effort to dump quality

RECORD TEMPLATE (produce when done — set record_complete: true in frontmatter to signal completion):

---
date: YYYY-MM-DD
type: decision | meeting-summary | discovery | context | problem-statement
status: active | tentative
record_complete: true
context_path: [project, subsystem, component]
people: [Name1, Name2]
supersedes: null
tags: [tag1, tag2]
decision: "1-2 sentence core takeaway"
---

## Rationale
## Alternatives considered
## Scope and boundaries
## Implications
## Open questions
## Ownership
## Context snapshot
## Raw input
> verbatim user dump

FIELD GUIDANCE:
- date: today unless user says otherwise
- type: infer from content
- status: default active, tentative only if user signals uncertainty
- context_path: ordered hierarchy, lowercase hyphenated slugs, consistent with existing records
- people: participants/decision-makers, not passing mentions
- supersedes: always null (system handles this)
- tags: 2-5, inferred
- decision: core takeaway, 1-2 sentences
- record_complete: always true on final output — never set during clarifying rounds
- Include only body sections with meaningful content

MULTI-RECORD SESSIONS:
If dump contains multiple unrelated items, say "I see a few separate things — let me handle them one at a time." Process each fully before the next.

EDGE CASES:
- Venting: acknowledge, ask if there's something to record
- "Just log it": respect it, infer what you can, mark gaps as [not discussed]
- User doesn't know: record that — "No alternatives evaluated due to time pressure" is valuable
- Undoing previous decision: reference naturally, leave supersedes null

TONE: Conversational, efficient. Trusted colleague with a notebook. Match user energy. Never bureaucratic.
```

---

### Prompt 2: Claim extraction

**When:** Step 3 of ingest pipeline (single call after extraction; may retry once after Step 4 validation).
**Input:** Full record markdown (frontmatter + body).
**Output:** JSON array of claims.

**System prompt:**

```
You are a claim extractor. You receive a structured decision record and decompose it into atomic claims.

A claim is a single factual assertion that could independently change without the rest of the record changing.

QUALIFIES AS A CLAIM:
- Technical choices: "Session data is stored in PostgreSQL"
- Parameters: "Token lifetime is 30 minutes"
- Constraints: "All auth endpoints must respond under 200ms"
- Rejections: "Redis was rejected for session storage due to operational overhead"
- Status: "The notifications service uses a background job processor"
- Ownership: "Carlos owns the session migration"

DOES NOT QUALIFY:
- Rationale attached to a choice (it's a property of the claim, not a separate claim)
- Opinions or sentiment
- Process descriptions
- Open questions
- Vague statements

GRANULARITY TEST: Could this change independently?
- Too coarse: "We redesigned auth to use JWT with 30-min tokens and refresh rotation" (3 things bundled)
- Too fine: "PostgreSQL is a relational database" (general knowledge)
- Right: "Auth tokens use JWT format" / "Token lifetime is 30 minutes" / "Refresh tokens rotate on each use"

Aim for 2-7 claims per record.

OUTPUT FORMAT: ONLY a JSON array. No preamble, no explanation, no markdown fencing.

[
  {"id": "c1", "content": "Session data is stored directly in PostgreSQL", "status": "active"},
  {"id": "c2", "content": "Redis is no longer used for session storage", "status": "active"}
]

FAILURE: If record is too vague for meaningful claims, return one weak claim summarizing core content with status "tentative".
```

---

### Prompt 3: Conflict evaluation

**When:** Step 7 of ingest pipeline (single call, skipped if no candidates).
**Input:** New claims + candidate existing claims from vector search and graph traversal (with metadata and `source: vector | graph`).
**Output:** JSON object with conflicts array.

**System prompt:**

```
You are a conflict evaluator for Yanka. You receive new claims and candidate existing claims from two sources: vector search (semantic neighbors) and graph traversal (active claims in the same context subtree). Determine which are genuine conflicts where the new supersedes the old. Graph-sourced candidates may use different wording but refer to the same subject — evaluate on meaning, not surface similarity.

CONFLICT = two claims make incompatible assertions about the same thing. Both cannot be true simultaneously in the same context.

CONFLICT EXAMPLES:
- "Token lifetime is 30 min" vs "Token lifetime is 15 min" → CONFLICT (same subject, different values)
- "Sessions in PostgreSQL" vs "Sessions in Redis" → CONFLICT (same subject, incompatible choices)

NOT A CONFLICT:
- Refinement: different aspects of the same system that coexist
- Different scope: different services, different projects
- Addition: new capability doesn't contradict existing
- Same assertion restated
- Different projects

EVALUATION: For each pair ask:
1. Same specific subject in same context?
2. Incompatible assertions?
3. Both yes = conflict

WHEN IN DOUBT: not a conflict. False positives are worse than false negatives.

OUTPUT: ONLY a JSON object. No preamble.

{"conflicts": [{"new_claim_id": "c1", "existing_claim_id": "2026-03-02-jwt-auth.md:c2", "reason": "Both specify token lifetime but with different values (30 min vs 15 min)"}]}

Or if none: {"conflicts": []}

FAILURE: return {"conflicts": []}
```

**Input format:**

```
NEW CLAIMS (being recorded now):
- c1: "Token lifetime is 30 minutes"
- c2: "Refresh tokens rotate on each use"

EXISTING CLAIMS (from vector search and graph — tag each with source):
- 2026-03-02-jwt-auth.md:c1: "Auth tokens use JWT format" [source: graph, project: main-platform, context: auth-service/token-management]
- 2026-03-02-jwt-auth.md:c2: "Token lifetime is 15 minutes" [source: vector, project: main-platform, context: auth-service/token-management]
```

---

### Prompt 4: Query analysis

**When:** Step 1 of retrieval pipeline (single call).
**Input:** User's raw question.
**Output:** JSON with query_type, filters, semantic_query, graph_hint.

**System prompt:**

```
You are a query analyzer for Yanka. Classify the question and extract structured filters for the retrieval system. You are NOT answering the question.

QUERY TYPES (exactly one):
- current_state: what's true now ("What's our auth approach?")
- historical: how something evolved ("How has our auth changed?")
- specific_decision: details of a known decision ("What did we decide about Redis?")
- exploratory: browsing/discovering ("Any decisions about security?")
- relationship: connections/impacts ("What did the K8s migration affect?")
- person: someone's involvement ("What has Carlos worked on?")

FILTERS (only include what's in the question):
- project: if mentioned
- context_keywords: systems, components, topics mentioned
- people: names mentioned
- time_range: {after, before} in YYYY-MM-DD. "Last month" = after first of last month. "Recently" = after 30 days ago. Omit if no time mentioned.
- status_filter: "active" for current_state, "all" for everything else unless query implies otherwise

SEMANTIC QUERY: 1-6 word phrase capturing the core concept. Strip meta-question words. "What did we decide about session storage?" → "session storage". Null if purely structural (person lookup, time listing).

GRAPH HINT: Brief natural language description of what graph traversal should do.

OUTPUT: ONLY a JSON object. No preamble.

{"query_type": "current_state", "filters": {"project": "main-platform", "context_keywords": ["auth", "session"], "status_filter": "active"}, "semantic_query": "session storage", "graph_hint": "Find active decisions under auth-related context nodes"}

FAILURE/VAGUE: default to {"query_type": "exploratory", "filters": {}, "semantic_query": null, "graph_hint": "List recent decisions across all projects"}
```

---

### Prompt 5: Retrieval synthesis

**When:** Step 4 of retrieval pipeline (single call).
**Input:** User's question + query type + retrieved records.
**Output:** Plain text answer with citations.

**System prompt:**

```
You are a knowledge retrieval assistant for Yanka. Synthesize a clear answer from the provided records.

RULES:
- Answer from records only, not general knowledge. Never fill gaps with what you know about a technology.
- Cite sources: every claim references its record as (source: filename.md).
- Respect supersession: latest active record is current truth. Mention history only if asked.
- Flag uncertainty: if records are incomplete or 3+ months old, say so.
- Don't editorialize: no opinions, no suggestions, no recommendations.

STRUCTURE BY QUERY TYPE:
- current_state: lead with the answer. Brief. Mention when decided.
- historical: chronological story. End with current state.
- specific_decision: full picture — what, why, alternatives, who, implications.
- exploratory: organize by theme/project. Brief per item.
- relationship: map connections and dependencies.
- person: list decisions by project or chronology. Brief summaries.

EDGE CASES:
- No relevant records: say so, suggest different terms.
- Records don't answer the question: state what you found, note the gap.
- Conflicting active records without supersession: flag the conflict.
- Stale records (3+ months): warn.

TONE: Direct, concise. No preamble. No explaining the retrieval process. Just answer.
```

**Input format:**

```
QUESTION: What's our current approach to session storage?

QUERY TYPE: current_state

RETRIEVED RECORDS:

--- record: 2026-05-14-drop-redis-sessions.md ---
[full record content]

--- record: 2026-02-10-redis-session-store.md ---
[full record content, status: superseded]
```

---

<a id="cli-ux"></a>
## 11. CLI UX

### Design principles

Rich and colorful for visual framework. Conversational and warm for interaction. Built with Python `rich` library.

### Commands

| Command          | Action                                                       |
|------------------|--------------------------------------------------------------|
| `/log`           | Start a recording session                                    |
| `/ask`           | Query existing knowledge                                     |
| `/resume`        | Continue an interrupted recording session                    |
| `/status`        | Record count, projects, recent activity                      |
| `/history`       | Recent records with summaries (alias: `/h`)                  |
| `/last`          | Show the most recent record                                  |
| `/people`        | List people in the graph with decision counts                |
| `/projects`      | List root context nodes (projects) with record counts        |
| `/config`        | Show effective configuration (no secret values)              |
| `/rebuild`       | Reconstruct graph + vectors from files                       |
| `/help`          | Command reference                                            |
| `/help <topic>`  | Contextual help for a specific command (`/log`, `/ask`, ...) |
| `/exit`          | Exit the REPL (aliases: `/quit`, `/q`)                       |

`/help` and `/?` are equivalent. All commands start with `/`; anything else
is treated as input only when explicitly prompted (e.g. inside `/log`).

### Top-level CLI subcommands

The REPL is the primary surface. The top-level `yanka` binary also exposes:

| Subcommand     | Action                                                                  |
|----------------|-------------------------------------------------------------------------|
| `yanka`        | Resolve paths, run first-run setup if needed, then enter the REPL       |
| `yanka rebuild`| One-shot graph + vector rebuild from `records/` (non-interactive)       |

`/resume` is REPL-only — there is no separate `yanka resume` subcommand.

### Color system

| Color | Meaning |
|---|---|
| Purple | System identity (yanka badge, section labels) |
| Blue | Interactive elements, citations, references |
| Amber/Yellow | Attention — conflicts, clarifying questions, staleness warnings |
| Green | Confirmed, active, success |
| Red | Superseded, replaced (strikethrough) |
| Gray | Metadata, timestamps, secondary information |

### Visual patterns

**System messages:** Purple `yanka` badge prefix, clear visual separation from user input.

**Clarifying questions:** Grouped in an indented block with left purple border. Numbered. Conversational tone.

**Conflict detection:** Amber left-border block. Shows old claim (red strikethrough) → new claim (green). Yes/no confirmation prompt.

**Record confirmation:** Green left-border block. Sections: context path, decision summary, claims list (tentative claims flagged), superseded records, tags, filename.

**Retrieval answer:** Subtle card background. Inline citations. Supersession timeline (vertical dots — green for active, hollow red for superseded). Source list with status badges. Staleness warning in amber.

**Thinking states:** Italic gray text: "searching for related records...", "extracting claims...", "validating claims...", "checking for conflicts..."

### First-run experience

```
$ yanka

  Welcome to yanka.

  Which LLM provider would you like to use?
  [1] Claude (recommended)
  [2] OpenAI
  [3] Google
  [4] Ollama (local)

  > 1

  API key: ****

  ✓ Ready. Your decisions will be stored in ~/.yanka/

  Type /log to record something, /ask to query, /help for more.

❯
```

---

<a id="error-handling"></a>
## 12. Error handling

### Principle

Never lose data. Always tell the user what happened. `yanka rebuild` is the
universal recovery. Detailed diagnostics go to the log file, not the terminal.

### Typed LLM error hierarchy

All LLM provider failures surface as subclasses of `LlmError`
(`src/yanka/llm/client.py`):

| Class                 | When it's raised                                  |
|-----------------------|---------------------------------------------------|
| `LlmAuthError`        | Provider rejected the API key                     |
| `LlmRateLimitError`   | Provider returned a rate-limit / quota error      |
| `LlmTimeoutError`     | The provider call exceeded the timeout            |
| `LlmTransportError`   | Network / 5xx / transient connection failure      |
| `LlmError`            | Any other LLM-related failure (catch-all)         |

Application code catches the subclass it cares about; the REPL catches
`LlmError` at the boundary and renders a user-facing message via
`src/yanka/repl/errors.py` (never a raw provider traceback).

### Retry-once policy

`LlmTransportError`, `LlmTimeoutError`, and `LlmRateLimitError` are retried
**once** silently inside the LLM client. `LlmAuthError` is never retried.
A second failure of any kind is raised to the caller.

### Pipeline failure modes

- **Extraction (Step 2):** no valid `record_complete` record after the
  conversation cap. The wrap-up prompt is issued; if the LLM still fails to
  return a valid record, the session is aborted with saved state for
  `/resume`. Nothing is written to the stores.

- **Claim extraction (Step 3) / claim validation (Step 4):** validation
  failure after one retry proceeds with claims as-is, flagged with an amber
  warning. Never blocks the write.

- **Entity resolution (Step 5) / conflict evaluation (Step 7):** on
  `LlmError`, degrade — entity resolution treats the new context as new,
  conflict evaluation defaults to an empty conflicts list — and continue with
  a warning. The record is still written.

- **Post-extraction abort (Steps 5–9):** if anything raises after a record
  exists in memory but before the write succeeds, the pipeline raises
  `IngestAbortError` carrying the failing stage and the in-memory record.
  The REPL persists this to `runtime/pending_log_session.json` and `/resume`
  replays the pipeline from the saved stage. No partial state is written to
  graph or vectors.

- **Query analysis (retrieval Step 1):** on failure, fall back to
  `query_type: exploratory` with a broad search.

- **Storage inconsistency (ingest Step 9):** markdown is always written
  first. If graph or vector update fails after, the failure is a warning,
  not fatal — the record exists; tell the user "indexing incomplete — run
  `/rebuild` to fix."

- **Stale index at retrieval time:** if merged retrieval hits reference
  markdown files that are no longer on disk, the missing files are skipped,
  retrieval continues with the rest, and a `STALE_INDEX_WARNING` (with a
  `/rebuild` hint) is attached to the result. If every hit is stale, a
  clean fallback answer is returned instead of crashing.

Never crash. Always degrade.

### User-facing messages

`src/yanka/repl/errors.py` maps exceptions to short messages. Examples:

| Failure              | Message shape                                              |
|----------------------|------------------------------------------------------------|
| `LlmAuthError`       | API key rejected — check keychain/env vars; `/resume`      |
| `LlmRateLimitError`  | Provider rate-limited — wait and `/resume`                 |
| `LlmTimeoutError`    | No response in time — `/resume` when ready                 |
| `LlmTransportError`  | Can't reach provider — check connection; `/resume`         |
| Other (`LlmError`)   | See `runtime/yanka.log`; `/resume`                         |

`click.Abort` (e.g. Ctrl-C during a conflict confirmation) is caught
explicitly in the REPL conflict path so the session does not bubble up an
ugly `Aborted!` line.

### Application logging

A bounded rotating log captures structured diagnostics:

- **File:** `<data_dir>/runtime/yanka.log`
- **Rotation:** 5 MB per file, 3 backups (bounded at ~20 MB total).
- **Contents:** exception tracebacks plus per-command context
  (`stage`, command name, key arguments). Configured by
  `src/yanka/app_logging.py`.
- **Test mode:** silenced in pytest runs.

Terminal output stays concise; the log is the source for post-mortems.

### Generic handler

For everything else (embedding model corruption, disk full, entity
resolution edge cases): the REPL prints a clear, action-oriented message,
logs the traceback to `yanka.log`, and points the user at `/rebuild` when
applicable. No silent failures, no stack traces in the terminal.

---

<a id="dependencies"></a>
## 13. Dependencies

### Core

| Package | Purpose |
|---|---|
| click | CLI framework |
| rich | Terminal formatting, colors, panels |
| litellm | LLM provider abstraction (Claude, OpenAI, Google, Ollama) |
| fastembed | Local embedding model (ONNX, no PyTorch) |
| ladybug | Embedded graph database (LadybugDB) |
| lancedb | Embedded vector database |
| pyyaml | YAML parsing for record frontmatter |
| keyring | System keychain for API key storage |

### Optional

| Package | Purpose |
|---|---|
| pytest | Testing |
| ruff | Linting |

---

<a id="decision-log"></a>
## 14. Decision log

| # | Decision | Rationale | Status |
|---|---|---|---|
| 1 | Filesystem as source of truth (no git) | Zero dependencies, simpler onboarding, cleaner cloud migration | Active |
| 2 | Two stores + filesystem (LadybugDB + LanceDB + markdown) | Each handles what it's best at. Graph and vector are rebuildable. | Active |
| 3 | App code as orchestrator, not LLM | Determinism, testability, predictable behavior | Active |
| 4 | No agent frameworks (no LangChain) | Fixed pipeline, plain Python more debuggable | Active |
| 5 | CLI first, cloud later | Validate core experience first | Active |
| 6 | Supersession is system-detected, user-confirmed | Users won't track supersession. Never silent. | Active |
| 7 | Claims as sub-structure of records | Enables partial supersession, preserves natural recording unit | Active |
| 8 | LadybugDB for graph | Embedded, serverless, Cypher, columnar | Active |
| 9 | LanceDB for vectors | Embedded, serverless, combined vector + metadata filtering | Active |
| 10 | FastEmbed + all-MiniLM-L6-v2 | Lightweight, local, behind swappable abstraction | Active |
| 11 | LiteLLM for LLM abstraction | Multi-provider support, default Claude | Active |
| 12 | Explicit commands (/log, /ask) | Zero-ambiguity vs implicit intent detection | Active |
| 13 | Independent retrieval sessions | Simpler for v1. Session mgmt deferred. | Active |
| 14 | Alias registry for entity resolution | Fuzzy matching + LLM fallback. Learns over time. | Active |
| 15 | Correction deferred to post-v1 | Record + supersede sufficient for launch | Deferred |
| 16 | Changelog as append-only JSONL | Audit trail, tamper detection via hash | Active |
| 17 | API keys in system keychain | Never stored in plaintext config files | Active |
| 18 | When in doubt, not a conflict | False positives worse than false negatives | Active |
| 19 | Rebuild as universal recovery | Reconstructs graph + vectors from files | Active |
| 20 | `record_complete: true` + required-key validation | Safe completion signal; bare `---` is insufficient | Active |
| 21 | Lightweight claim validation after extraction | Catches record/claim drift; one retry, never blocks write | Active |
| 22 | Graph + vector conflict candidate search | Graph catches structural/context conflicts; vector catches semantic neighbors | Active |
| 23 | Typed `LlmError` hierarchy + retry-once on transient | Lets app code decide how to handle each failure; one silent retry catches flaky networks/rate limits without re-prompting the user | Active |
| 24 | Post-extraction degrade + stage-aware `/resume` | Once a record exists in memory, never throw it away — degrade entity resolution / conflict eval, or persist `IngestAbortError` stage for `/resume` | Active |
| 25 | Stale-index resilience over crash on missing records | Retrieval skips merged hits whose markdown file is gone, surfaces a `/rebuild` warning, and falls back cleanly when everything is stale | Active |
| 26 | Bounded rotating file log under `runtime/` | Keeps detailed diagnostics for post-mortems without unbounded growth (5 MB × 3 backups, ~20 MB cap) and without cluttering the terminal | Active |
| 27 | Parameterized Cypher + consolidated `MERGE … ON CREATE/MATCH SET` | Removes manual escaping risk and halves graph-write round trips during ingest/rebuild | Active |
| 28 | Graph inspection commands as pure app code (`/people`, `/projects`, `/config`) | Read-only queries over the graph and config — no LLM needed; cheap, deterministic answers | Active |
| 29 | Statusline record-count cache with directory-fingerprint invalidation | Avoids re-scanning `records/` on every prompt keystroke; invalidates on writes from `/log` and `/resume` | Active |

---

