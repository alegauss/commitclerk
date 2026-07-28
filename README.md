<div align="center">

<img src="docs/logo.png" alt="commitclerk logo" width="112" height="112">

# commitclerk

**Write better git commit messages in one command — powered by your staged diff and an LLM.**

[![PyPI](https://img.shields.io/pypi/v/commitclerk.svg)](https://pypi.org/project/commitclerk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Zero dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#requirements)
[![CI](https://github.com/alegauss/commitclerk/actions/workflows/ci.yml/badge.svg)](https://github.com/alegauss/commitclerk/actions/workflows/ci.yml)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-fe5196.svg)](https://www.conventionalcommits.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[Website](https://alegauss.github.io/commitclerk/) · [Quick start](#quick-start) · [Usage](#usage) · [Why it exists](#why-it-exists) · [Configuration](#configuration) · [Contributing](CONTRIBUTING.md) · [Português](README.pt-BR.md)

</div>

---

A *clerk* records what actually happened. `commitclerk` reads your staged diff, asks an LLM for a Conventional Commits message, shows it to you, and commits — in a single Python file with **zero dependencies**, small enough that you can read the whole thing before letting it near your source code.

```console
$ git add .
$ clerk

--- commit message ---
fix: prevent duplicate webhook deliveries on retry

- Deduplicate by delivery id before enqueueing, so a provider retry no
  longer fans out into multiple downstream jobs.
- Store the id in the existing idempotency table instead of a new one,
  keeping the retention policy in a single place.
- Log a debug line on the dedupe path to make retry storms visible.
----------------------
[main a1b2c3d] fix: prevent duplicate webhook deliveries on retry
```

## Highlights

| | |
|---|---|
| 🪶 **Zero dependencies** | Standard library only (`urllib`, `subprocess`, `argparse`). Drop the file in and run it. |
| 🔗 **Git-native** | Installs as `git clerk` too, so it lives where the rest of your git muscle memory already is. |
| ✍️ **You can own the title** | `-m "feat: add X"` uses your title verbatim and lets the AI write only the body. |
| 📄 **Doc-aware** | Detects documentation-only commits and refuses to describe already-shipped features as new work. See [Why it exists](#why-it-exists). |
| 🧾 **Conventional Commits** | Emits `feat:` / `fix:` / `docs:` / `chore:` / `refactor:` / `test:` / `build:` / `perf:` prefixes. |
| 👀 **Dry run** | `--dry-run` prints the message and commits nothing. |
| 🔧 **Model agnostic** | Any OpenAI Chat Completions model via `--model` or `$OPENAI_MODEL`. Providers live in a small adapter table selected by `--provider`. |
| 📐 **Fair on big commits** | Oversized diffs are trimmed per file, not cut off at the end, so the last file changed is never invisible to the model. |

## Requirements

- **Python 3.8+** — no third-party packages
- **git** on your `PATH`
- An **OpenAI API key** in `OPENAI_API_KEY`

## Quick start

**1. Install**

```bash
pipx install commitclerk    # recommended
# or
pip install commitclerk
```

Or skip installing entirely — it is one file with no dependencies, so this works
just as well:

```bash
curl -O https://raw.githubusercontent.com/alegauss/commitclerk/main/commitclerk.py
python commitclerk.py --help
```

**2. Set your API key**

```bash
# macOS / Linux
export OPENAI_API_KEY="sk-..."
```

```powershell
# Windows (PowerShell, persisted for future sessions)
setx OPENAI_API_KEY "sk-..."
```

**3. Stage and commit**

```bash
git add .
clerk --dry-run   # look before you leap
clerk             # or: git clerk
```

## Usage

```
clerk [-m TITLE] [--dry-run] [--provider NAME] [--model MODEL] [--max-chars N] [--version]
```

Installing gives you three identical entry points: `clerk`, `commitclerk`, and
`git clerk` — git runs any `git-<name>` on your `PATH` as a subcommand, so
`git add -A && git clerk` reads like git rather than like a bolt-on. If you run
the file directly instead, replace `clerk` with `python commitclerk.py` in every
example below.

| Flag | Default | What it does |
|---|---|---|
| `-m`, `--message TITLE` | — | Use `TITLE` verbatim as the commit title; the AI writes only the body bullets. |
| `--dry-run` | off | Print the generated message and exit without committing. |
| `--provider NAME` | `openai` (or `$CLERK_PROVIDER`) | Which API provider to call. `openai` today; more providers are added to the same adapter table. |
| `--model MODEL` | the provider's default — `gpt-4o-mini` (or `$OPENAI_MODEL`) for `openai` | Model to call. |
| `--max-chars N` | `60000` | Character budget for the diff. A larger diff is trimmed **per file**, so every changed file still reaches the model. |
| `--version` | — | Print the version and exit. |

### Examples

```bash
# Let the AI write the whole message
clerk

# You choose the title, the AI writes the body — the most reliable mode
clerk -m "refactor: extract retry policy into its own module"

# Preview only, never commits
clerk --dry-run

# Use a stronger model for a large or subtle change
clerk --model gpt-4o

# Very large diff: raise the budget so less of each file is trimmed
clerk --max-chars 120000
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Committed (or `--dry-run` printed the message). |
| `1` | Nothing staged — run `git add` first. |
| `2` | Configuration problem — the provider's API key is not set, or `--provider` names a provider that does not exist. |
| other | Passed through from `git commit`. |

## Wrappers

Two convenience wrappers do the same three things: check the API key, stage everything with `git add -A`, then call `commitclerk.py` with whatever arguments you pass through.

```bat
REM Windows
run-commit.cmd -m "feat: add CSV export to the reports page"
```

```bash
# macOS / Linux
./run-commit.sh -m "feat: add CSV export to the reports page"
```

Put the repo directory (or a copy of the wrapper plus `commitclerk.py`) on your `PATH` to call it from any repo.

> **Heads up:** the wrappers stage everything, including new, deleted and dot-prefixed files. If you prefer to curate what goes into the commit, stage it yourself and call `python commitclerk.py` directly. The Python script never stages anything on its own.

If you'd rather not use a wrapper at all, a shell alias does the same job:

```bash
alias ac='git add -A && clerk'
```

## Why it exists

Most commit-message generators only see the diff, and that is a real blind spot. When a commit adds prose to a `CHANGELOG`, `ROADMAP`, or `README` **describing a feature that shipped three commits ago**, a naive generator reads that prose and writes:

```
feat: implement real-time collaboration
```

…for a commit that changed nothing but Markdown. Your history is now lying to you, and `git log --grep` and release tooling inherit the lie.

`commitclerk` handles this in two ways:

1. **Documentation-only detection.** If every staged file is documentation — `.md`, `.mdx`, `.rst`, `.txt`, `.adoc`, anything under `docs/`, or a known name like `CHANGELOG`/`README`/`ROADMAP`/`CONTRIBUTING` — the prompt switches to a docs-only framing: use the `docs:` prefix and describe *the documentation change itself* ("record X in the changelog"), never "implement X".

2. **`-m` as an override.** You know what your change is. `-m "<title>"` pins the title and reduces the model's job to summarizing the diff underneath it. This is the recommended default for any commit whose intent isn't obvious from the diff alone.

The same rule set also keeps titles imperative and under 72 characters, keeps bodies to 2–6 bullets about *why* rather than a file-by-file replay, and bans emojis, headers, and code fences.

## How it works

```
git diff --staged ──▶ per-file budget (--max-chars) ──▶ doc-only? ──▶ build prompt
                                                                          │
                                        provider API (--provider) ◀────────┘
                                                │
                              message ──▶ print ──▶ git commit -F -
```

The whole thing is ~440 lines in [`commitclerk.py`](commitclerk.py). It's meant to be read, forked, and adapted to your team's conventions — start with the `_RULES` string.

## Configuration

There is no configuration file (yet). Everything is a flag or an environment
variable, and **a flag always beats the environment**:

| Variable | Used by | What it sets |
|---|---|---|
| `OPENAI_API_KEY` | `openai` | The API key. Required; read from the environment only, never written to disk. |
| `OPENAI_MODEL` | `openai` | Default model, when `--model` is not given. |
| `CLERK_PROVIDER` | all | Default provider, when `--provider` is not given. |

Providers are a table of four slots in [`commitclerk.py`](commitclerk.py) — URL,
headers, request payload, response extractor. Adding one is a table entry, not a
new abstraction layer; `openai` is the only entry today.

```bash
# Pin a model for one repository, without touching your global environment
OPENAI_MODEL=gpt-4o clerk -m "fix: reject expired tokens on refresh"
```

## Privacy and cost

- **Your staged diff is sent to the OpenAI API.** Do not run this on repositories whose contents cannot leave your machine. Check your employer's policy first.
- Nothing else is transmitted, stored, or logged by this tool: no telemetry, no analytics, no remote config.
- The API key is read from the environment and never written to disk.
- Cost is a single Chat Completions call per commit. With the default `gpt-4o-mini` and a typical diff, that is a fraction of a cent.

## Troubleshooting

<details>
<summary><strong>"No staged changes. Run <code>git add &lt;files&gt;</code> first."</strong></summary>

Nothing is staged. `commitclerk.py` deliberately never stages for you — run `git add` (or use `run-commit.cmd` / `run-commit.sh`, which stage everything).
</details>

<details>
<summary><strong>"Error: OPENAI_API_KEY is not set."</strong></summary>

Export the key in the shell you are actually using. On Windows, `setx` only affects **new** terminals — reopen yours after running it.
</details>

<details>
<summary><strong>"OpenAI API error 401 / 429"</strong></summary>

`401` means the key is invalid or revoked. `429` means rate-limited or out of quota — check your usage at the OpenAI dashboard, or retry with a smaller `--max-chars`.
</details>

<details>
<summary><strong>The message describes the wrong thing</strong></summary>

Use `-m "<your title>"`. The AI then writes only the body, and the framing of the commit is yours.
</details>

<details>
<summary><strong>The diff got truncated</strong></summary>

The diff budget is 60 000 characters by default. Past that, each file is trimmed to a fair share and marked with `[... N lines truncated ...]` — every file still reaches the model, but large ones arrive incomplete. Raise the budget with `--max-chars`, or — better — split the change into smaller commits.
</details>

## Roadmap

The full backlog lives in **[`docs/ROADMAP.md`](docs/ROADMAP.md)**, with the design
rationale behind each item in [`docs/IMPROVEMENTS.md`](docs/IMPROVEMENTS.md) and the
project's positioning and non-goals in [`docs/STRATEGY.md`](docs/STRATEGY.md).

Ideas that would make good first contributions:

- [ ] `prepare-commit-msg` git hook installer (T36)
- [ ] Support for additional providers — Anthropic, Azure OpenAI, Ollama / local models (T2–T4)
- [ ] Interactive `--edit` mode that opens the message in `$EDITOR` before committing (T31)
- [ ] A configuration file for project-specific commit rules (T25)
- [ ] `clerk --lint`: validate an existing message with no API call, as a `commit-msg` hook (T28)
- [ ] A demo GIF or asciinema cast for the top of this README (T49)

Grab one, or propose your own in an [issue](https://github.com/alegauss/commitclerk/issues).

## Contributing

Contributions are very welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) for the ground rules — the short version is: keep it dependency-free, keep it one file, and open an issue before a large change.

Also see the [Code of Conduct](CODE_OF_CONDUCT.md) and the [security policy](SECURITY.md).

## License

[MIT](LICENSE) © Alexandre Oliveira

---

<div align="center">
If this saves you from one more <code>git commit -m "fix stuff"</code>, consider leaving a ⭐.
</div>
