# Phase S — dependency spikes

Disposable tests that validate third-party libraries before we build product wrappers.

## Install

```bash
pip install -e ".[dev,spike]"
```

## Run

```bash
# Main suite (no spike deps required)
pytest

# Spikes only (explicit path; `spikes` is in pytest norecursedirs)
YANKA_RUN_SPIKES=1 pytest tests/spikes -v
```

Set `YANKA_RUN_SPIKES=1` to enable live Ollama checks in S.3. Without it, import-only tests still run; the live completion is skipped.

## Findings (for Phase 2–3)

### Ladybug (S.1)

- Package: `pip install ladybug`, import as `import ladybug as lb`
- API: `lb.Database(path)`, `lb.Connection(db)`, `conn.execute(cypher)`
- Node/rel DDL: `CREATE NODE TABLE`, `CREATE REL TABLE` with `FROM` / `TO`
- Inserts: `CREATE (n:Label {prop: value})` or `COPY FROM` for bulk

### LanceDB (S.2)

- Local path URI; tables created from PyArrow schema or `create_table`
- Vector search via `.search(vector).limit(n)`
- Metadata filters via SQL/predicate on the table API version in use

### LiteLLM + Ollama (S.3)

- Model id: `ollama/qwen3:8b`
- `api_base`: `http://127.0.0.1:11434` (default Ollama)
- No API key for local Ollama
- **Qwen3:** pass `extra_body={"think": False}` or LiteLLM returns empty `message.content` (Ollama puts output in `thinking` when think mode is on)
