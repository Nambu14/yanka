# yanka

**Log engineering decisions in conversation. Find them later with plain English.**

yanka is a local-first CLI for your own engineering memory. You `/log` what you decided; it becomes structured markdown on disk. You `/ask` a question months later and get answers with citations — no digging through notes, no "why did I choose this again?"

Your data stays on your machine. Markdown is the source of truth; search indexes rebuild from files anytime.

---

## Install

**Requirements:** Python 3.12 or newer.

### pip (macOS, Linux, Windows)

```bash
pip install yanka
```

### Homebrew (macOS)

```bash
brew tap Nambu14/yanka
brew install yanka
```

---

## Quick start

```bash
yanka
```

On first run, yanka creates `~/.yanka` and walks you through LLM provider setup (Claude, OpenAI, Google, or local Ollama). Then you're in the REPL:

```text
/log We chose Postgres over Dynamo for the audit trail — I know SQL, need ad-hoc queries
/ask Why did we pick Postgres for audit?
```

| Command | What it does |
|---------|----------------|
| `/log [text]` | Capture a decision (inline or guided) |
| `/ask [question]` | Query your knowledge base with citations |
| `/rebuild` | Re-index from markdown if something looks stale |
| `/help` | Full command list |

---

## What yanka does

- **Capture** — free-form `/log` notes become structured decision records (markdown + metadata).
- **Index** — local graph + vector store for semantic and relational retrieval.
- **Retrieve** — `/ask` answers with links to the records that support them.
- **Recover** — indexes are disposable; `/rebuild` reconstructs everything from files alone.

Everything lives under `~/.yanka/`:

```
~/.yanka/
├── records/          # Markdown records (source of truth)
├── graph/            # LadybugDB index (rebuildable)
├── vectors/          # LanceDB index (rebuildable)
└── config.yaml       # Provider, models, paths
```

---

## First-run defaults

The setup wizard picks a fast/cheap default model per provider (similar tier to `gpt-4o-mini`):

| Provider | Default model |
|----------|----------------|
| Claude | `claude-3-5-haiku-latest` |
| OpenAI | `gpt-4o-mini` |
| Google | `gemini-2.0-flash-lite` |
| Ollama | `llama3.2:3b` |

Change models in `config.yaml` or inspect effective values with `/config`.

---

## Common recovery flows

- **Stale index warning in `/ask`** — run `/rebuild`, then retry.
- **Interrupted `/log`** — run `/resume`.
- **Something broke** — check `~/.yanka/runtime/yanka.log`.

---

## Developing

Clone the repo and install with dev dependencies:

```bash
git clone https://github.com/Nambu14/yanka.git
cd yanka
pip install -e ".[dev]"
pytest -q
```

See [`docs/architecture.md`](docs/architecture.md) and [`yanka-spec.md`](yanka-spec.md) for the full product and data model.

---

## Releases (maintainers)

Nothing runs on push or tag by itself. You cut a release when you choose.

### CI on pull requests and `main`

The [CI workflow](.github/workflows/ci.yml) runs on every pull request and on pushes to `main` (lint + full test suite). Merge only after CI is green.

### Release flow

The **git tag is the version** — there is no version string to edit in source. [`hatch-vcs`](https://github.com/ofek/hatch-vcs) derives it from the latest `v*` tag.

**Actions → Release → Run workflow** — enter the version, run. No version-bump commit or PR.

| Input | Meaning |
|-------|---------|
| **version** | e.g. `0.3.0` (no `v` prefix) |
| **publish** | `false`: draft GitHub Release only. `true`: publish release + upload to PyPI. |

The workflow builds on macOS, Linux, and Windows, creates tag `v<version>`, attaches release assets (including `yanka-<version>.tar.gz` for Homebrew), and optionally publishes to [PyPI](https://pypi.org/project/yanka/).

After a draft release, open **Releases** on GitHub and click **Publish** when ready.

Update the [homebrew-yanka](https://github.com/Nambu14/homebrew-yanka) tap via **Actions → Update formula** (opens a PR with url + sha256 from the release).

Local build:

```bash
pip install build
python scripts/build_release.py --version 0.3.0
ls release/
```

---

## License

Apache License 2.0 — see [`LICENSE`](LICENSE).

## Documentation

- Product spec: [`yanka-spec.md`](yanka-spec.md)
- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Operations runbook: [`docs/operations.md`](docs/operations.md)
- Future ideas: [`docs/future-improvements.md`](docs/future-improvements.md)
- Archived v1 build plan: [`docs/archive/IMPLEMENTATION.md`](docs/archive/IMPLEMENTATION.md)
