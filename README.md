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
| 🏠 **Writes like your repo** | Reads your last 200 commits to learn the types, scopes, body shape and language your team actually uses, and shows the model the past commits that touched these same files as worked examples. The message belongs in *your* history instead of being generically correct. Local, no extra API call. |
| 📦 **Monorepo-aware scopes** | Staged files are walked up to the nearest workspace manifest, so a change confined to one package becomes `fix(billing-api): …`. Spread across packages, it refuses to name one and hide the rest. |
| 👀 **Dry run** | `--dry-run` prints the message and commits nothing. |
| 🔧 **Model agnostic** | OpenAI, Anthropic or a local Ollama model via `--provider`, any model via `--model`, and any OpenAI-compatible endpoint via `--base-url`. |
| 💬 **You can tell it why** | `--context "this reverts the caching experiment"` for one commit, and a committed `.clerk/context.md` for the standing facts about your repo. The one thing a diff can never show, said once instead of guessed at. |
| ⚙️ **Config file per project** | A committed `.clerk.json` picks the provider, model, endpoint and budgets for everyone on the team, so a convention stops being flags each person retypes. Flags and environment variables still win over it. |
| 🎫 **Ticket trailers** | Turn on `ticket_refs` and the issue key in your branch (`feat/PROJ-123-…`) becomes a `Refs: PROJ-123` trailer — Jira, Linear and GitHub out of the box. Off by default, and read off the branch rather than asked of the model, so it cannot be invented. |
| 🚫 **Per-file veto, not per-repo** | A `.clerkignore` (same syntax as `.gitignore`) withholds a matched file's **contents**: the model gets its name and line counts and a placeholder. That's what lets a security team say yes to a repo with three sensitive files instead of no to the whole repo. Runs before the secret scan, so it's also the clean way out of a false positive. |
| ✈️ **Works with the network down** | `--offline` writes a deterministic message with no API call, no key and no model — type from the file classes, scope from the workspace manifest, bullets grouped by directory. It never guesses `feat:` or `fix:`, so it is a draft, not a replacement. An outage or an expired key stops being a broken git workflow. |
| 🛡️ **Refuses to leak a secret** | A staged `.env` is scanned *before* the first request, not after: known key shapes and high-entropy tokens on added lines stop the run with exit `3`, naming the file and line and never the match. This tool sits upstream of every secret-scanning hook you already have, so it was the blind spot. `--redact` masks instead of refusing; `--no-scan` opts out. |
| 🔒 **Runs offline if you want** | `--provider ollama` needs no API key and talks to `localhost` — your diff never leaves the machine. |
| 🔁 **Survives a rate limit** | Transient `429`/`5xx` replies are retried with backoff and jitter, honouring `Retry-After`, instead of losing the commit — and a model that rejects a parameter gets the request repaired and resent. |
| 🗂️ **Classifies what changed** | Each file is typed as `code` · `test` · `docs` · `generated` · `config` · `vendor` · `binary`, so a lockfile or a `vendor/` bump never becomes the subject of your commit message. |
| 🧭 **Sees what the diff hides** | Renames, mode changes, deletions and binary file *sizes* come from `git --stat --summary`, so a `git mv` is described as a move rather than a rewrite. |
| 📐 **Fair on big commits** | Oversized diffs are trimmed per file, not cut off at the end, so the last file changed is never invisible to the model — and lockfiles and `vendor/` bumps are collapsed to one line so they stop crowding out your actual change. |
| 🔬 **Scales past the context window** | For the 5 000-line commit that fits in no budget, `--deep` summarises each oversized file in its own cheap request and writes the message from those summaries plus the smaller files' real diffs — so the tail of the change is *described* instead of trimmed away. Opt-in, because it costs a request per big file. |

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
clerk [-m TITLE] [--context NOTE] [--dry-run] [--provider NAME] [--base-url URL]
      [--model MODEL] [--timeout S] [--max-chars N] [--deep] [--no-house-style]
      [--no-examples] [--redact] [--no-scan] [--offline] [--version]
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
| `--context NOTE` | — | One sentence of intent the diff cannot show, e.g. `"this reverts the caching experiment"`. Standing facts about the repository belong in `.clerk/context.md` instead. |
| `--dry-run` | off | Print the generated message and exit without committing. |
| `--provider NAME` | `openai` (or `$CLERK_PROVIDER`) | Which provider to call: `openai`, `anthropic`, or `ollama` (local, no key). |
| `--base-url URL` | `https://api.openai.com/v1` (or `$OPENAI_BASE_URL`) | Point at any **OpenAI-compatible** endpoint — Ollama, LM Studio, vLLM, llama.cpp, OpenRouter, Groq, Together, Azure. |
| `--model MODEL` | the provider's default — `gpt-4o-mini` (or `$OPENAI_MODEL`) for `openai` | Model to call. |
| `--timeout S` | `60` | Seconds to wait for each API request. Raise it for a slow local model. |
| `--max-chars N` | `60000` | Character budget for the diff. A larger diff is trimmed **per file**, so every changed file still reaches the model; generated and vendored files are collapsed to a one-line placeholder first. |
| `--deep` | off | For a commit no budget can fit: summarise each **oversized** file in its own cheap request, then write the message from those summaries plus the smaller files' real diffs. Costs one extra request per oversized file — and nothing at all when the diff already fits. |
| `--no-house-style` | off | Skip the `git log` behind both the house-style fingerprint and the worked examples. Use it when the history is imported or machine-generated, or to keep past commit message text off the wire. |
| `--no-examples` | off | Send no past commit message **text**, but keep the fingerprint, which reports only counts and shapes. The narrow half of `--no-house-style`, for a team that will share a statistic about its history but not the history itself. Implied by `--no-house-style`. |
| `--offline` | off | Write the message locally: no API call, no key, no network. Type from the file classes, scope from the workspace manifest, bullets grouped by directory. It **never** emits `feat:` or `fix:` — those state intent, which nothing local can see — so treat it as a draft. Use it on a plane, during an outage, or with an expired key. |
| `--redact` | off | When the pre-flight scan finds a suspected secret, mask it in the request and carry on instead of refusing. **The commit is unchanged and still contains it** — this protects what is sent, not what is committed. |
| `--no-scan` | off | Do not scan the staged diff for secrets before sending it. Turns off `--redact` along with it, there being nothing left to mask. |
| `--version` | — | Print the version and exit. |

Every default in that table can also come from a [config file](#configuration) —
`.clerk.json` in the repository, or `~/.config/clerk/config.json` for your own
machine. A flag always wins over both.

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

# A 5000-line commit no budget can fit: summarise the big files instead of
# trimming them away, so the tail of the change is described too
clerk --deep

# A local model, so the diff never leaves your machine — no API key needed
clerk --provider ollama

# A slow local model: wait longer per request
clerk --provider ollama --timeout 300

# Fresh fork with an imported history you do not want copied
clerk --no-house-style

# Copy the conventions, but keep past commit message text off the wire
clerk --no-examples

# The scan flagged something you know is a fixture: mask it and carry on
# (the commit still contains it — this only protects the request)
clerk --redact

# On a plane, mid-outage, or with an expired key: a local deterministic draft
clerk --offline

# Offline, but you know the intent — the best of both, and still no API call
clerk --offline -m "fix: stop the retry storm"

# Tell it the one thing the diff cannot show
clerk --context "this reverts the caching experiment we ran last sprint"

# Set the team's choice once, in the repository, instead of on every commit
echo '{"provider": "anthropic", "timeout": 120}' > .clerk.json
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Committed (or `--dry-run` printed the message). |
| `1` | Nothing staged — run `git add` first. |
| `2` | Configuration problem — the provider's API key is not set, `--provider` names a provider that does not exist, or a config file cannot be read as written. |
| `3` | The pre-flight scan found a suspected secret in the staged diff. **Nothing was sent.** Its own code, so a wrapper can tell "you nearly leaked a key" apart from "your API key is not set". |
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
git diff --staged ──▶ .clerkignore: matched bodies withheld ────────┐
      └──▶ secret scan: refuse (exit 3), or --redact ───────────────┤
      └──▶ per-file budget (--max-chars) ──▶ doc-only? ─────────────┤
      └──▶ oversized files ──▶ one summary each (--deep) ───────────┤
git diff --stat --summary ──▶ renames, modes, binary sizes ─────────┤
git log -n200 ──▶ house style: types, scopes, body shape, language ─┤
            └──▶ past commits about these files ──▶ worked examples ─┤
nearest workspace manifest ──▶ inferred scope ──────────────────────┴──▶ prompt
                                                                          │
                                        provider API (--provider) ◀────────┘
                                                │
                              message ──▶ print ──▶ git commit -F -

--offline skips the two boxes on the right: the message is written from the
left column alone, so no prompt is built and no provider is ever resolved.
```

The source is a fourteen-module package under [`commitclerk/`](commitclerk/) — `config`,
`context`, `excludes`, `diffing`, `deep`, `files`, `secrets`, `offline`, `history`,
`gitio`, `trailers`, `prompt`, `providers`, `cli` — and
[`scripts/build_single_file.py`](scripts/build_single_file.py) concatenates it into
[`dist/commitclerk.py`](dist/commitclerk.py) (3122 lines, no imports beyond the
standard library) so the audit-and-copy path survives. CI rebuilds the artifact, fails
if it is stale, and runs the whole test suite against it as well as against the
package. It's meant to be read, forked, and adapted to your team's conventions — start
with the `_RULES` string in [`commitclerk/prompt.py`](commitclerk/prompt.py).

## Configuration

A setting can come from five places. They are consulted in one fixed order, and
the first one that has an answer wins:

**command-line flag → environment variable → `.clerk.json` in the repository →
`~/.config/clerk/config.json` → built-in default**

### The config file

`.clerk.json` sits at the **root of the repository** and is meant to be committed:
it is how a team's convention stops being flags each person retypes. The same
file at `~/.config/clerk/config.json` sets your own defaults across every
repository, and any project that disagrees overrides it.

```json
{
  "provider": "anthropic",
  "model": "claude-haiku-4-5",
  "timeout": 120,
  "max_chars": 90000,
  "house_style": true
}
```

| Key | Type | Equivalent flag |
|---|---|---|
| `provider` | string | `--provider` |
| `model` | string | `--model` |
| `base_url` | string | `--base-url` |
| `timeout` | number | `--timeout` |
| `max_chars` | number | `--max-chars` |
| `scan` | boolean | `false` is `--no-scan` (the one setting that defaults to **on**) |
| `house_style` | boolean | `false` is `--no-house-style` |
| `examples` | boolean | `false` is `--no-examples` (ignored under `"house_style": false`, which already refuses both) |
| `deep` | boolean | `true` is `--deep` |
| `ticket_refs` | boolean | — (off by default; see below) |
| `ticket_pattern` | string | — (implies `ticket_refs`) |
| `assisted_by` | boolean | — (off by default; adds an `Assisted-by:` trailer, see below) |

The file is found from the repository root, not the directory you are standing
in, so the tool behaves the same three levels down. API keys are **not** settings:
they are read from the environment only, never from a file. A key the tool does
not recognise is reported on stderr and ignored, so a config written for a newer
version still works; a file that is not valid JSON, or a value of the wrong type,
is an error (exit `2`) rather than a setting silently dropped.

> A committed `.clerk.json` can set `base_url`, which is **where your diff is
> sent**. Read it as you would any other file you run code from — see
> [SECURITY.md](SECURITY.md).

### Keeping a file's contents off the wire

A repository with three sensitive files should not have to refuse the tool
outright. `.clerkignore` at the repository root makes that call **per file**:

```gitignore
# .clerkignore — same syntax as .gitignore
secrets/
*.env
!.env.example
config/production.json
```

A matched file keeps its diff header and its line counts and loses its body. The
model sees `- secrets/prod.env (config, excluded)` in the file list and
`[... excluded by .clerkignore, +12 -3, contents not shown ...]` where the diff
would be, so the message can say the file changed without its contents leaving
the machine.

> **The paths are still sent.** Only contents are withheld. If a *filename* cannot
> be disclosed either, use `--offline`, which makes no request at all, or don't run
> the tool on that repository.

It runs **before** the secret scan, which makes it the clean way out of a false
positive: content that is never transmitted has nothing to refuse over, so you
do not have to turn the whole scan off with `--no-scan`.

Supported: `#` comments, blank lines, `!` negation (the last matching rule wins),
`/`-anchored patterns, trailing `/` for a directory, `*` (stops at a `/`) and `**`
(does not). Anything this subset cannot honour — a backslash separator, a rule
that matches nothing — is an **error** (exit `2`) naming the line, never a pattern
that silently does nothing. A rule that quietly does nothing is a file quietly
transmitted.

Like `.clerk.json`, it is found from the repository root and meant to be committed:
exclusion is a property of the repository, and a personal copy would mean a
teammate's run transmits what yours withheld.

### Telling it what the diff cannot show

A diff shows *what* changed. It never shows why, and no amount of reading it
recovers that. Two ways to say it:

```bash
# This once
clerk --context "this reverts the caching experiment we ran last sprint"
```

```
.clerk/context.md   — standing facts, committed with the repo

  The CLI installs as `clerk`; the product is called commitclerk.
  Everything under docs/ is internal and not published.
  We deploy on Thursdays, so a Friday hotfix is unusual.
```

`--context` is for this commit; `.clerk/context.md` is for every commit, read
verbatim on each run. Both are strictly additive to the prompt — they can only
inform the message, never change what the tool does — and both are told to
explain the *why* rather than be restated as work this commit performed. Keep the
file to a few lines: it comes out of the same `--max-chars` budget as the diff,
and is truncated at 2 000 characters.

### Ticket trailers

Your branch name usually already says which ticket you are on, and the diff never
does. Turn `ticket_refs` on and the issue key in the branch becomes a `Refs:`
trailer, so the link between a commit and its ticket stops being retyped:

```json
{ "ticket_refs": true }
```

```
Branch:  feat/PROJ-123-retry-webhooks

feat(webhooks): retry a failed delivery three times

- because a single 5xx should not drop the event

Refs: PROJ-123
```

The built-in pattern is `[A-Z]{2,10}-\d+|#\d+`, which covers Jira, Linear and
GitHub. Set `ticket_pattern` to your own regex for anything else — doing so turns
the feature on by itself, so there is no second key to remember. This is **off
until you ask for it**: a `Refs:` trailer on a repository with no tracker is
noise, and the tool does not add ceremony to your history uninvited.

The key is read off the branch and appended to the finished message, never sent
to the model, so it cannot be paraphrased or invented. A branch with no key
produces no trailer, a trailer you already wrote is not repeated, and an existing
trailer block is joined rather than duplicated.

### Recording that a commit was AI-assisted

Some organisations now require it. Set `"assisted_by": true` and the finished
message gains one trailer:

```
Assisted-by: commitclerk 0.2.1 (gpt-4o-mini)
```

**Off by default, and there is no flag** — for the same reason `ticket_refs` has
none. Whether your history carries provenance is something a repository decides
once, not something each commit re-argues, and an unrequested watermark in
someone else's git log is a non-goal of this project.

`--offline` calls no model, so it says so:

```
Assisted-by: commitclerk 0.2.1 (offline, no model)
```

Naming a model there would be the tool recording work that did not happen, which
is the one thing it exists not to do — and it keeps the two cases apart for the
`git log --grep="Assisted-by"` that is the whole point of writing it down.

The key is fixed and not configurable: one that varied per repository would
defeat that grep. When `ticket_refs` is on too, `Refs:` comes first — that one is
about the work, this one about how the message was written. Both are appended
after the model has answered, so neither can be paraphrased or invented, and a
re-run does not state either twice.

### Environment variables

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

- **A `.clerkignore` withholds a file's contents entirely.** Same syntax as `.gitignore`, read from the repository root. A matched file reaches the model as its path, its line counts and a `[... excluded ...]` placeholder — never its body. Applied before the secret scan and before any request. **The paths themselves are still sent**; only contents are withheld. See [Keeping a file's contents off the wire](#keeping-a-files-contents-off-the-wire).
- **Nothing is sent until the staged diff has been scanned for secrets.** Before the first request, every *added* line is checked for known credential shapes (`sk-`, `ghp_`, `github_pat_`, `AKIA`, `xox…`, `AIza`, `-----BEGIN … PRIVATE KEY-----`, JWTs) and for high-entropy tokens. A hit **refuses the run** with exit `3`, naming the file, the line and which detector fired — never the match itself, because a terminal is somewhere a secret gets copied out of. This runs on the diff *as staged*, before trimming and before `--deep`'s extra requests, so there is no path that sends first and checks later. `--redact` masks and continues; `--no-scan` or `"scan": false` turns it off.
- **Your staged diff is sent to the API you configured** — `https://api.openai.com/v1` by default, or Anthropic's API with `--provider anthropic`, or whatever `--base-url` or a `.clerk.json` in the repository names. On a repository whose contents may not leave your machine, run `--provider ollama` (a local model, no key, nothing over the network) or don't run the tool there at all. Check your employer's policy first.
- **Some of your recent commit *messages* are sent too.** The house-style block carries counts and shapes measured from the last 200 subjects and bodies — types, scopes, body shape, median subject length, trailer keys, language — not the messages themselves, except scope names and trailer keys, which appear verbatim because counting them would be useless. Separately, the two or three past commits that touched the same files as your staged diff are sent **verbatim** as style examples, subject plus body clipped to 400 characters, with trailer blocks (and the email addresses in them) stripped first. No diff, author, email, date or SHA from history is read. Those are two different data flows and each has its own switch: `--no-examples` drops the verbatim messages and keeps the counts, and `--no-house-style` skips the `git log` and both of them.
- Nothing else is transmitted, stored, or logged by this tool: no telemetry, no analytics, no remote config.
- The API key is read from the environment and never written to disk.
- Cost is a single API call per commit. With either provider's default model and a typical diff, that is a fraction of a cent.
- **`--deep` changes both of those numbers.** It spends one extra request per file too large for the budget, and each of those requests carries that file's diff **in full** rather than the trimmed share `--max-chars` would have sent. Same endpoint, same key, same provider — more of your code, and N+1 calls instead of one. It is off by default for exactly that reason, and a commit that already fits the budget triggers none of it.

## Troubleshooting

<details>
<summary><strong>"No staged changes. Run <code>git add &lt;files&gt;</code> first."</strong></summary>

Nothing is staged. `commitclerk` deliberately never stages for you — run `git add` (or use `run-commit.cmd` / `run-commit.sh`, which stage everything).
</details>

<details>
<summary><strong>"the staged diff contains N possible secrets; nothing was sent." (exit <code>3</code>)</strong></summary>

The pre-flight scan matched a known credential shape or a high-entropy token on an added line. **Nothing left your machine.** Each line is named as `path:line (detector)`.

If it is a real secret, unstage the file (`git restore --staged .env`) and add it to `.gitignore` — the scan is telling you about the commit, not just the request.

If it is a fixture, an example key or a hash the heuristic misread, either `--redact` (masks it in the request and commits anyway, so the secret is still in your history) or `--no-scan` (sends it as-is). A repository whose history is full of legitimate high-entropy strings can set `"scan": false` in `.clerk.json`, but prefer `--no-scan` per run: the default is on because the cost of being wrong is not reversible.
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
