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

A *clerk* records what actually happened. `commitclerk` reads your staged diff, asks an LLM for a Conventional Commits message, shows it to you, and commits — with **zero dependencies** — and it still ships as [one readable file](dist/commitclerk.py) you can audit before letting it near your source code.

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
| 📄 **Doc-aware** | Detects documentation commits — pure *and* mixed with code — and refuses to describe already-shipped features as new work. See [Why it exists](#why-it-exists). |
| 🧾 **Conventional Commits** | Emits `feat:` / `fix:` / `docs:` / `chore:` / `refactor:` / `test:` / `build:` / `perf:` prefixes. |
| 🏠 **Writes like your repo** | Reads your last 200 commits to learn the types, scopes, body shape and language your team actually uses, so the message belongs in *your* history instead of being generically correct. Local, no extra API call. |
| 📦 **Monorepo-aware scopes** | Staged files are walked up to the nearest workspace manifest, so a change confined to one package becomes `fix(billing-api): …`. Spread across packages, it refuses to name one and hide the rest. |
| 👀 **Dry run** | `--dry-run` prints the message and commits nothing. |
| 🔧 **Model agnostic** | OpenAI, Anthropic or a local Ollama model via `--provider`, any model via `--model`, and any OpenAI-compatible endpoint via `--base-url`. |
| 🔒 **Runs offline if you want** | `--provider ollama` needs no API key and talks to `localhost` — your diff never leaves the machine. |
| 🔁 **Survives a rate limit** | Transient `429`/`5xx` replies are retried with backoff and jitter, honouring `Retry-After`, instead of losing the commit — and a model that rejects a parameter gets the request repaired and resent. |
| 🗂️ **Classifies what changed** | Each file is typed as `code` · `test` · `docs` · `generated` · `config` · `vendor` · `binary`, so a lockfile or a `vendor/` bump never becomes the subject of your commit message. |
| 🧭 **Sees what the diff hides** | Renames, mode changes, deletions and binary file *sizes* come from `git --stat --summary`, so a `git mv` is described as a move rather than a rewrite. |
| 📐 **Fair on big commits** | Oversized diffs are trimmed per file, not cut off at the end, so the last file changed is never invisible to the model — and lockfiles and `vendor/` bumps are collapsed to one line so they stop crowding out your actual change. |

## Requirements

- **Python 3.8+** — no third-party packages
- **git** on your `PATH`
- An **API key** — `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY` with `--provider anthropic`. No key at all with `--provider ollama`, which talks to a local model instead.

## Quick start

**1. Install**

```bash
pipx install commitclerk    # recommended
# or
pip install commitclerk
```

Or skip installing entirely. The source is a small package, and every change is
rebuilt into one standalone file with no dependencies, so this works just as well:

```bash
curl -O https://raw.githubusercontent.com/alegauss/commitclerk/main/dist/commitclerk.py
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
clerk [-m TITLE] [--dry-run] [--provider NAME] [--base-url URL] [--model MODEL]
      [--timeout S] [--max-chars N] [--no-house-style] [--version]
```

Installing gives you three identical entry points: `clerk`, `commitclerk`, and
`git clerk` — git runs any `git-<name>` on your `PATH` as a subcommand, so
`git add -A && git clerk` reads like git rather than like a bolt-on. If you run
the tool from a repository checkout instead, replace `clerk` with
`python -m commitclerk`; if you downloaded the single file, use
`python commitclerk.py`.

| Flag | Default | What it does |
|---|---|---|
| `-m`, `--message TITLE` | — | Use `TITLE` verbatim as the commit title; the AI writes only the body bullets. |
| `--dry-run` | off | Print the generated message and exit without committing. |
| `--provider NAME` | `openai` (or `$CLERK_PROVIDER`) | Which provider to call: `openai`, `anthropic`, or `ollama` (local, no key). |
| `--base-url URL` | `https://api.openai.com/v1` (or `$OPENAI_BASE_URL`) | Point at any **OpenAI-compatible** endpoint — Ollama, LM Studio, vLLM, llama.cpp, OpenRouter, Groq, Together, Azure. |
| `--model MODEL` | the provider's default — `gpt-4o-mini` (or `$OPENAI_MODEL`) for `openai` | Model to call. |
| `--timeout S` | `60` | Seconds to wait for each API request. Raise it for a slow local model. |
| `--max-chars N` | `60000` | Character budget for the diff. A larger diff is trimmed **per file**, so every changed file still reaches the model; generated and vendored files are collapsed to a one-line placeholder first. |
| `--no-house-style` | off | Skip the `git log` that measures your repo's own conventions. Use it when the history is imported, machine-generated, or otherwise not a style you want copied. |
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

# A local model, so the diff never leaves your machine — no API key needed
clerk --provider ollama

# A slow local model: wait longer per request
clerk --provider ollama --timeout 300

# Fresh fork with an imported history you do not want copied
clerk --no-house-style
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Committed (or `--dry-run` printed the message). |
| `1` | Nothing staged — run `git add` first. |
| `2` | Configuration problem — the provider's API key is not set, or `--provider` names a provider that does not exist. |
| other | Passed through from `git commit`. |

## Wrappers

Two convenience wrappers do the same three things: check the API key, stage everything with `git add -A`, then run `commitclerk` with whatever arguments you pass through.

```bat
REM Windows
run-commit.cmd -m "feat: add CSV export to the reports page"
```

```bash
# macOS / Linux
./run-commit.sh -m "feat: add CSV export to the reports page"
```

Put the repo directory (or a copy of the wrapper plus the downloaded `commitclerk.py`) on your `PATH` to call it from any repo — the wrappers add their own directory to `PYTHONPATH`, so either layout works.

> **Heads up:** the wrappers stage everything, including new, deleted and dot-prefixed files. If you prefer to curate what goes into the commit, stage it yourself and call `python -m commitclerk` directly. The Python code never stages anything on its own.

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

1. **Documentation detection, in two flavours.** If every staged file is documentation — `.md`, `.mdx`, `.rst`, `.txt`, `.adoc`, anything under `docs/`, or a known name like `CHANGELOG`/`README`/`ROADMAP`/`CONTRIBUTING` — the prompt switches to a docs-only framing: use the `docs:` prefix and describe *the documentation change itself* ("record X in the changelog"), never "implement X".

   The harder case is the **mixed** commit, which is also the common one: a big CHANGELOG entry *plus* a one-line fix. There, the prompt names the documentation files, states documentation's share of the changed lines, and instructs the model to take the type prefix only from the non-documentation diff lines — so a docstring tweak beside 48 lines of changelog prose comes back as `docs:`, not `feat:`. A commit that genuinely implements a feature *and* documents it still gets `feat:`; the guard checks the code, it does not just ban the word.

2. **`-m` as an override.** You know what your change is. `-m "<title>"` pins the title and reduces the model's job to summarizing the diff underneath it. This is the recommended default for any commit whose intent isn't obvious from the diff alone.

A second blind spot is *proportion*. A three-line bug fix that also regenerates
`package-lock.json` is a bug fix, but the lockfile is 12 000 lines of the diff.
`commitclerk` classifies every staged file — `code`, `test`, `docs`, `generated`,
`config`, `vendor`, `binary` — annotates the file list with those classes, and
instructs the model to take the commit type from the files that are the *point* of
the change and never to make generated, vendored or binary files the subject.

Classification also decides what is worth sending. A generated or vendored file's
diff body is replaced by a single line naming it and counting its changes, which
happens *before* the per-file budget so the space goes to the code instead. On a
real repository, a 300-package lockfile bump next to a two-line bug fix shrank from
39 505 characters of diff to 342 — with the two-line fix intact.

A third blind spot is structural: a unified diff does not say that a file was
*renamed* (unless the repo has rename detection on), that its permissions changed,
or how large a binary file became. `commitclerk` sends `git diff --staged
--find-renames --stat --summary` alongside the diff, so those facts are stated
rather than guessed — and because that summary is small, it survives intact even
when a large diff has been trimmed.

The same rule set also keeps titles imperative and under 72 characters, keeps bodies to 2–6 bullets about *why* rather than a file-by-file replay, and bans emojis, headers, and code fences.

## How it works

```
git diff --staged ──▶ per-file budget (--max-chars) ──▶ doc-only? ──┐
git diff --stat --summary ──▶ renames, modes, binary sizes ─────────┤
git log -n200 ──▶ house style: types, scopes, body shape, language ─┤
nearest workspace manifest ──▶ inferred scope ──────────────────────┴──▶ prompt
                                                                          │
                                        provider API (--provider) ◀────────┘
                                                │
                              message ──▶ print ──▶ git commit -F -
```

The source is a seven-module package under [`commitclerk/`](commitclerk/) — `diffing`,
`files`, `history`, `gitio`, `prompt`, `providers`, `cli` — and
[`scripts/build_single_file.py`](scripts/build_single_file.py) concatenates it into
[`dist/commitclerk.py`](dist/commitclerk.py) (1496 lines, no imports beyond the
standard library) so the audit-and-copy path survives. CI rebuilds the artifact, fails
if it is stale, and runs the whole test suite against it as well as against the
package. It's meant to be read, forked, and adapted to your team's conventions — start
with the `_RULES` string in [`commitclerk/prompt.py`](commitclerk/prompt.py).

## Configuration

There is no configuration file (yet). Everything is a flag or an environment
variable, and **a flag always beats the environment**:

| Variable | Used by | What it sets |
|---|---|---|
| `OPENAI_API_KEY` | `openai` | The API key. Required; read from the environment only, never written to disk. |
| `OPENAI_MODEL` | `openai` | Default model, when `--model` is not given. |
| `OPENAI_BASE_URL` | `openai` | Default endpoint, when `--base-url` is not given. |
| `ANTHROPIC_API_KEY` | `anthropic` | The API key. Required for `--provider anthropic`. |
| `ANTHROPIC_MODEL` | `anthropic` | Default model, when `--model` is not given. |
| `ANTHROPIC_BASE_URL` | `anthropic` | Default endpoint, when `--base-url` is not given. |
| `OLLAMA_MODEL` | `ollama` | Default model, when `--model` is not given. |
| `OLLAMA_BASE_URL` | `ollama` | Default endpoint, when `--base-url` is not given. |
| `CLERK_PROVIDER` | all | Default provider, when `--provider` is not given. |

Providers are a table of four slots in [`commitclerk/providers.py`](commitclerk/providers.py) — URL,
headers, request payload, response extractor. Adding one is a table entry, not a
new abstraction layer.

### Providers

| `--provider` | Endpoint | Key | Default model |
|---|---|---|---|
| `openai` | `https://api.openai.com/v1/chat/completions` | `OPENAI_API_KEY` | `gpt-4o-mini` |
| `anthropic` | `https://api.anthropic.com/v1/messages` | `ANTHROPIC_API_KEY` | `claude-haiku-4-5` |
| `ollama` | `http://localhost:11434/v1/chat/completions` | none | `qwen2.5-coder` |

```bash
# Anthropic, cheap default
ANTHROPIC_API_KEY="sk-ant-..." clerk --provider anthropic

# Anthropic, stronger model for a subtle change
clerk --provider anthropic --model claude-opus-5 -m "refactor: split the retry policy out"

# Make it the default for this shell
export CLERK_PROVIDER=anthropic
```

Both defaults are deliberately small, cheap models — a commit message is a short
summary of a diff, not a reasoning problem, and this runs on every commit. Reach
for `--model` when a change is subtle enough to need it.

```bash
# Pin a model for one repository, without touching your global environment
OPENAI_MODEL=gpt-4o clerk -m "fix: reject expired tokens on refresh"
```

### OpenAI-compatible endpoints

Most vendors speak the OpenAI wire format, so `--base-url` covers them with no new
code and no new dependency. A local Ollama server already has a preset —
`--provider ollama`, which points at `localhost` and asks for no key — so
`--base-url` is for everything else:

```bash
# LM Studio (local)
OPENAI_API_KEY=lmstudio clerk --base-url http://localhost:1234/v1 --model your-loaded-model

# A hosted gateway (OpenRouter, Groq, Together, Azure, …)
clerk --base-url https://openrouter.ai/api/v1 --model anthropic/claude-3.5-sonnet
```

Two honest caveats: small local models write noticeably weaker bodies than a
hosted frontier model — `-m "<title>"` helps a lot there — and a custom endpoint
is a **different destination for your diff**, so point it somewhere you trust.

## Privacy and cost

- **Your staged diff is sent to the API you configured** — `https://api.openai.com/v1` by default, or Anthropic's API with `--provider anthropic`, or whatever `--base-url` names. On a repository whose contents may not leave your machine, run `--provider ollama` (a local model, no key, nothing over the network) or don't run the tool there at all. Check your employer's policy first.
- **A summary of your recent commit *messages* is sent too.** The house-style block carries counts and shapes measured from the last 200 subjects and bodies — types, scopes, body shape, median subject length, trailer keys, language — not the messages themselves. Scope names and trailer keys are the exception and appear verbatim, since counting them would be useless. No diff, author, email, date or SHA from history is read. `--no-house-style` skips the `git log`.
- Nothing else is transmitted, stored, or logged by this tool: no telemetry, no analytics, no remote config.
- The API key is read from the environment and never written to disk.
- Cost is a single API call per commit. With either provider's default model and a typical diff, that is a fraction of a cent.

## Troubleshooting

<details>
<summary><strong>"No staged changes. Run <code>git add &lt;files&gt;</code> first."</strong></summary>

Nothing is staged. `commitclerk` deliberately never stages for you — run `git add` (or use `run-commit.cmd` / `run-commit.sh`, which stage everything).
</details>

<details>
<summary><strong>"Error: OPENAI_API_KEY is not set." (or <code>ANTHROPIC_API_KEY</code>)</strong></summary>

Each provider reads its own key variable — see [Configuration](#configuration). Export it in the shell you are actually using. On Windows, `setx` only affects **new** terminals — reopen yours after running it.
</details>

<details>
<summary><strong>"OpenAI API error 401 / 429" (or "Anthropic API error ...")</strong></summary>

The message is prefixed with the provider that rejected the call. `401` means the key is invalid or revoked, and fails immediately. `429` and `5xx` are transient, so they are retried twice with backoff and jitter (honouring `Retry-After`) before giving up — if you still see the error, you are genuinely out of quota. Check your usage on that provider's dashboard, or retry with a smaller `--max-chars`.
</details>

<details>
<summary><strong>"Unsupported parameter" / "does not support temperature"</strong></summary>

You should not see this: a `400` naming a parameter `commitclerk` sent is repaired
automatically — the parameter is dropped, or renamed when the provider's message
says which name to use — and the request is retried once. A line on stderr says what
changed. If the error survives that, the model is rejecting something the request
cannot do without; pick a different `--model`.
</details>

<details>
<summary><strong>"Note: 1 staged file has unstaged changes too"</strong></summary>

You staged part of a file and then kept editing (or used `git add -p`). The message
describes what you staged, which is correct — but it is not what is on disk right
now. Stage the rest with `git add <file>` and re-run if you meant to include it. The
note goes to stderr, so it never lands in a piped message.
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
- [ ] Interactive `--edit` mode that opens the message in `$EDITOR` before committing (T31)
- [ ] A configuration file for project-specific commit rules (T25)
- [ ] `clerk --lint`: validate an existing message with no API call, as a `commit-msg` hook (T28)
- [ ] A demo GIF or asciinema cast for the top of this README (T49)

Grab one, or propose your own in an [issue](https://github.com/alegauss/commitclerk/issues).

## Contributing

Contributions are very welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) for the ground rules — the short version is: keep it dependency-free, keep the single-file build working, and open an issue before a large change.

Also see the [Code of Conduct](CODE_OF_CONDUCT.md) and the [security policy](SECURITY.md).

## License

[MIT](LICENSE) © Alexandre Oliveira

---

<div align="center">
If this saves you from one more <code>git commit -m "fix stuff"</code>, consider leaving a ⭐.
</div>
