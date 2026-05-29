# yanka

Capture engineering decisions from natural conversation, turn them into
structured records, and retrieve them later with natural language.

## What yanka does

- Converts free-form `/log` notes into structured markdown decision records.
- Indexes records into a local graph + vector store for retrieval.
- Answers `/ask` questions with citations to matching records.
- Keeps markdown files as the source of truth; indexes are disposable and
  recoverable with `/rebuild`.

## Install

```bash
pip install -e ".[dev]"
```

## First run

```bash
yanka
```

On first run, yanka initializes your data directory (default `~/.yanka`) and
walks through provider/key setup. The wizard sets `llm.provider` and the
default `llm.model` for that provider (fast/cheap tier, similar to
`gpt-4o-mini`):

| Provider | Default model |
|----------|----------------|
| Claude | `claude-3-5-haiku-latest` |
| OpenAI | `gpt-4o-mini` |
| Google | `gemini-2.0-flash-lite` |
| Ollama | `llama3.2:3b` |

Change models in `config.yaml` or inspect effective values with `/config`.

## Data layout

```
~/.yanka/
├── records/                # Markdown records (source of truth)
├── changelog.jsonl         # Append-only record operations
├── graph/                  # LadybugDB index (rebuildable)
├── vectors/                # LanceDB index (rebuildable)
├── runtime/                # runtime logs and pending resume state
└── config.yaml             # effective configuration
```

## Core commands (REPL)

- `/log [text]` - record a decision (inline or prompted)
- `/ask [question]` - query indexed knowledge
- `/resume` - continue interrupted `/log`
- `/rebuild` - rebuild graph/vector indexes from markdown files
- `/status`, `/history`, `/last` - inspect local records
- `/people`, `/projects`, `/config` - inspect graph/config state
- `/help [topic]` - command help
- `/exit` - quit

## Common recovery flows

- **Stale index warning in `/ask`**
  - Run `/rebuild`, then retry `/ask`.
- **Interrupted logging session**
  - Run `/resume`.
- **Unexpected provider/runtime error**
  - Check `~/.yanka/runtime/yanka.log` (rotated, bounded file logs).

## Logging

yanka writes application logs to `runtime/yanka.log` in your data directory
with rotation:

- `maxBytes=5_000_000`
- `backupCount=3`

## Releases (manual)

Nothing runs on push or tag by itself. You cut a release when you choose.

### CI on pull requests and `main`

The [CI workflow](.github/workflows/ci.yml) runs on every pull request and on pushes to `main` (lint + full test suite). Merge only after CI is green.

### Release flow (today)

Merge feature PRs to `main` as usual — **no separate version-bump PR**. Version lives only in [`pyproject.toml`](pyproject.toml); `yanka --version` reads it from there (or from installed package metadata).

**Actions → Release → Run workflow** — enter the version, run.

| Input | Meaning |
|-------|---------|
| **version** | e.g. `0.2.0` (no `v` prefix) |
| **publish** | `false` (default): draft release for review. `true`: publish immediately and create tag `v0.2.0`. |

The workflow then:

1. Commits `chore(release): bump version to …` on `main` (only `pyproject.toml`).
2. Builds on **macOS**, **Linux**, and **Windows** from that commit.
3. Creates a **GitHub Release** with **`yanka-<version>.tar.gz`** (sdist, for Homebrew) plus platform bundles (tag points at the bump commit).
4. Keeps copies on the workflow run under **Artifacts**.

Each bundle (`yanka-<version>-<os>-<arch>.tar.gz`, or `.zip` on Windows) contains:

| File | Purpose |
|------|---------|
| `yanka-<version>.tar.gz` | Source distribution (sdist) — usual input for a Homebrew formula `url` + `sha256` |
| `yanka-<version>-py3-none-any.whl` | Wheel for `pip install` smoke checks |
| `SHA256SUMS.txt` | Checksums for files in the bundle |
| `MANIFEST.txt` | Version, platform, and Python used for the build |

After a draft release, open **Releases** on GitHub and click **Publish** when ready.

**Repo settings:** the workflow must be allowed to push to `main` (Settings → Actions → General → Workflow permissions, and branch protection must allow `github-actions[bot]` if enabled).

Local build (same packages as CI):

```bash
pip install build
python scripts/build_release.py --version 0.2.0
ls release/
```

### Homebrew tap

The [homebrew-yanka](https://github.com/Nambu14/homebrew-yanka) formula downloads **`yanka-<version>.tar.gz`** from the GitHub Release (`…/releases/download/v<version>/yanka-<version>.tar.gz`), not the platform bundles and not GitHub’s “Source code” archive.

After you publish a release:

1. `curl -L "https://github.com/Nambu14/yanka/releases/download/v0.2.0/yanka-0.2.0.tar.gz" | shasum -a 256`
2. In **homebrew-yanka**, run **Actions → Update formula** with that version and sha256.

### Release flow (later, optional)

A fuller “click once” flow could:

- Read **Conventional Commits** since the last tag and bump **major/minor/patch** automatically.
- Generate **changelog** text from commit messages.
- Open a PR that bumps `pyproject.toml` / `__init__.py`, then tag and release when merged.

Tools that do that include [release-please](https://github.com/googleapis/release-please) or [python-semantic-release](https://python-semantic-release.readthedocs.io/). That is not wired up yet; the workflow above is the deliberate simple version: **you choose the version, CI builds and attaches everything to a GitHub Release.**

## License

Apache License 2.0 — see [`LICENSE`](LICENSE).

## Documentation

- Product spec: [`yanka-spec.md`](yanka-spec.md)
- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Operations runbook: [`docs/operations.md`](docs/operations.md)
- Future ideas: [`docs/future-improvements.md`](docs/future-improvements.md)
- Archived v1 build plan: [`docs/archive/IMPLEMENTATION.md`](docs/archive/IMPLEMENTATION.md)
