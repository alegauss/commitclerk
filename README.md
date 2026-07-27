<div align="center">

# ai-commit

**Write better git commit messages in one command — powered by your staged diff and an LLM.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Zero dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#requirements)
[![CI](https://github.com/alegauss/ai-commit/actions/workflows/ci.yml/badge.svg)](https://github.com/alegauss/ai-commit/actions/workflows/ci.yml)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-fe5196.svg)](https://www.conventionalcommits.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[Quick start](#quick-start) · [Usage](#usage) · [Why it exists](#why-it-exists) · [Configuration](#configuration) · [Contributing](CONTRIBUTING.md) · [Português](README.pt-BR.md)

</div>

---

`ai-commit` is a single Python file — **no packages to install, no virtualenv, no lockfile**. It reads your staged diff, asks an LLM for a Conventional Commits message, shows it to you, and commits.

```console
$ git add .
$ python ai_commit.py

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
| ✍️ **You can own the title** | `-m "feat: add X"` uses your title verbatim and lets the AI write only the body. |
| 📄 **Doc-aware** | Detects documentation-only commits and refuses to describe already-shipped features as new work. See [Why it exists](#why-it-exists). |
| 🧾 **Conventional Commits** | Emits `feat:` / `fix:` / `docs:` / `chore:` / `refactor:` / `test:` / `build:` / `perf:` prefixes. |
| 👀 **Dry run** | `--dry-run` prints the message and commits nothing. |
| 🔧 **Model agnostic** | Any OpenAI Chat Completions model via `--model` or `$OPENAI_MODEL`. |

## Requirements

- **Python 3.8+** — no third-party packages
- **git** on your `PATH`
- An **OpenAI API key** in `OPENAI_API_KEY`

## Quick start

**1. Get the script**

```bash
git clone https://github.com/alegauss/ai-commit.git
cd ai-commit
```

Or just download the single file:

```bash
curl -O https://raw.githubusercontent.com/alegauss/ai-commit/main/ai_commit.py
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
python ai_commit.py --dry-run   # look before you leap
python ai_commit.py
```

## Usage

```
python ai_commit.py [-m TITLE] [--dry-run] [--model MODEL] [--max-chars N]
```

| Flag | Default | What it does |
|---|---|---|
| `-m`, `--message TITLE` | — | Use `TITLE` verbatim as the commit title; the AI writes only the body bullets. |
| `--dry-run` | off | Print the generated message and exit without committing. |
| `--model MODEL` | `gpt-4o-mini` (or `$OPENAI_MODEL`) | Chat Completions model to call. |
| `--max-chars N` | `60000` | Truncate the diff to `N` characters before sending it to the API. |

### Examples

```bash
# Let the AI write the whole message
python ai_commit.py

# You choose the title, the AI writes the body — the most reliable mode
python ai_commit.py -m "refactor: extract retry policy into its own module"

# Preview only, never commits
python ai_commit.py --dry-run

# Use a stronger model for a large or subtle change
python ai_commit.py --model gpt-4o

# Very large diff: send more context
python ai_commit.py --max-chars 120000
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Committed (or `--dry-run` printed the message). |
| `1` | Nothing staged — run `git add` first. |
| `2` | `OPENAI_API_KEY` is not set. |
| other | Passed through from `git commit`. |

## Windows wrapper

`run-commit.cmd` is a convenience wrapper for Windows: it checks the API key, runs `git add *`, then calls `ai_commit.py` with whatever arguments you pass through.

```bat
run-commit.cmd -m "feat: add CSV export to the reports page"
```

Put the repo directory (or a copy of both files) on your `PATH` to call it from any repo:

```bat
run-commit.cmd
```

> **Heads up:** the wrapper stages everything with `git add *`. If you prefer to curate what goes into the commit, stage it yourself and call `python ai_commit.py` directly. The Python script never stages anything on its own.

On macOS and Linux, use the script directly — a shell alias does the same job:

```bash
alias aic='git add -A && python /path/to/ai_commit.py'
```

## Why it exists

Most commit-message generators only see the diff, and that is a real blind spot. When a commit adds prose to a `CHANGELOG`, `ROADMAP`, or `README` **describing a feature that shipped three commits ago**, a naive generator reads that prose and writes:

```
feat: implement real-time collaboration
```

…for a commit that changed nothing but Markdown. Your history is now lying to you, and `git log --grep` and release tooling inherit the lie.

`ai-commit` handles this in two ways:

1. **Documentation-only detection.** If every staged file is documentation — `.md`, `.mdx`, `.rst`, `.txt`, `.adoc`, anything under `docs/`, or a known name like `CHANGELOG`/`README`/`ROADMAP`/`CONTRIBUTING` — the prompt switches to a docs-only framing: use the `docs:` prefix and describe *the documentation change itself* ("record X in the changelog"), never "implement X".

2. **`-m` as an override.** You know what your change is. `-m "<title>"` pins the title and reduces the model's job to summarizing the diff underneath it. This is the recommended default for any commit whose intent isn't obvious from the diff alone.

The same rule set also keeps titles imperative and under 72 characters, keeps bodies to 2–6 bullets about *why* rather than a file-by-file replay, and bans emojis, headers, and code fences.

## How it works

```
git diff --staged ──▶ truncate to --max-chars ──▶ doc-only? ──▶ build prompt
                                                                    │
                                     Chat Completions API ◀─────────┘
                                                │
                              message ──▶ print ──▶ git commit -F -
```

The whole thing is ~230 lines in [`ai_commit.py`](ai_commit.py). It's meant to be read, forked, and adapted to your team's conventions — start with the `_RULES` string.

## Privacy and cost

- **Your staged diff is sent to the OpenAI API.** Do not run this on repositories whose contents cannot leave your machine. Check your employer's policy first.
- Nothing else is transmitted, stored, or logged by this tool: no telemetry, no analytics, no remote config.
- The API key is read from the environment and never written to disk.
- Cost is a single Chat Completions call per commit. With the default `gpt-4o-mini` and a typical diff, that is a fraction of a cent.

## Troubleshooting

<details>
<summary><strong>"No staged changes. Run <code>git add &lt;files&gt;</code> first."</strong></summary>

Nothing is staged. `ai_commit.py` deliberately never stages for you — run `git add` (or use `run-commit.cmd`, which stages everything).
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

Diffs are cut at 60 000 characters by default. Raise it with `--max-chars`, or — better — split the change into smaller commits.
</details>

## Roadmap

Ideas that would make good first contributions:

- [ ] A POSIX `run-commit.sh` wrapper to match `run-commit.cmd`
- [ ] `prepare-commit-msg` git hook installer
- [ ] Support for additional providers (Anthropic, Azure OpenAI, Ollama / local models)
- [ ] Interactive `--edit` mode that opens the message in `$EDITOR` before committing
- [ ] A configuration file for project-specific commit rules

Grab one, or propose your own in an [issue](https://github.com/alegauss/ai-commit/issues).

## Contributing

Contributions are very welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) for the ground rules — the short version is: keep it dependency-free, keep it one file, and open an issue before a large change.

Also see the [Code of Conduct](CODE_OF_CONDUCT.md) and the [security policy](SECURITY.md).

## License

[MIT](LICENSE) © Alexandre Oliveira

---

<div align="center">
If this saves you from one more <code>git commit -m "fix stuff"</code>, consider leaving a ⭐.
</div>
