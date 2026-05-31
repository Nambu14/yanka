# yanka

<p align="left">
  <a href="https://pypi.org/project/yanka/"><img src="https://img.shields.io/pypi/v/yanka.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/yanka/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg?logo=python&logoColor=white" alt="Python 3.12+"></a>
  <a href="https://github.com/Nambu14/yanka/actions/workflows/ci.yml"><img src="https://github.com/Nambu14/yanka/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://github.com/Nambu14/yanka/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Nambu14/yanka.svg" alt="License"></a>
</p>

**Capture technical decisions fast. Retrieve the why later.**

Yanka is a local-first CLI for individual engineering memory. You use `/log` to turn a messy decision note into a structured markdown record on disk, with context and claims that stay readable by humans.

Later, you use `/ask` in plain English and get a direct answer with source citations from your own records. No note archaeology, no vendor lock-in, no mystery about why a decision was made.

## Demo
*Log a brain dump, answer a few clarifying questions, get a structured record.*

![Log a decision with /log](docs/demos/log-flow.gif)


*Ask in plain English and get a cited answer from your own records.*

![Ask later with /ask](docs/demos/ask-flow.gif)

## Quick Install (Fastest Path)

```bash
pip install yanka
yanka
```

Python 3.12+ required. On first run, Yanka asks for a data directory and LLM provider, then drops you into the REPL.

## Try It Now

Run this exact sequence:

```text
/log We moved auth session storage from Redis to Postgres so ops is simpler and debugging is SQL-first.
/ask Why did we move auth session storage to Postgres?
```

Useful commands you will use immediately:

- `/log [text]` — capture a decision (inline or prompted)
- `/ask [question]` — query your knowledge base with citations
- `/rebuild` — rebuild graph/vector indexes from markdown records
- `/resume` — continue interrupted `/log` work
- `/help` — command reference

## The Two Main Flows

### 1) Log a decision, note, or claim

Use `/log` with inline text or start `/log` and paste when prompted.

```text
/log We standardized on feature flags per service to reduce release risk.
```

Yanka runs its ingest pipeline, asks clarifying questions when needed, and writes a record under `~/.yanka/records/`.

### 2) Ask later and retrieve the reasoning

Use `/ask` with a natural-language question.

```text
/ask Why did we standardize on feature flags per service?
```

Yanka searches your local knowledge base and returns an answer with citations to the relevant record files.

## Why Yanka Exists

- Engineering context decays fast; decisions get buried in chat, docs, and memory.
- Engineers need a lightweight way to capture rationale at decision time, not in a template-heavy process later.
- You should be able to dump messy thoughts quickly and let Yanka turn them into structured records with minimal back-and-forth.
- When you ask later, answers should come back with high certainty and source citations, not guesses.
- Markdown files are the source of truth, so your data is portable and inspectable.
- Graph and vector indexes are rebuildable with `yanka rebuild`, so recovery is straightforward.

## What Makes It Different

- Conversational capture (`/log`) instead of forms
- Plain-English retrieval (`/ask`) with citations
- Local-first by default
- File-backed and rebuildable, not a black box

## Optional Install Notes

### Homebrew (macOS)

```bash
brew tap Nambu14/yanka
brew install yanka
```

## Contributing

```bash
git clone https://github.com/Nambu14/yanka.git
cd yanka
pip install -e ".[dev]"
pytest -q
```

Useful docs:

- Product spec: [`yanka-spec.md`](yanka-spec.md)
- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Operations: [`docs/operations.md`](docs/operations.md)
- Future ideas: [`docs/future-improvements.md`](docs/future-improvements.md)

## Next Step

Install Yanka, run `yanka`, and log one real decision from this week.  
Then run `/ask` and confirm you can recover the context in seconds.
