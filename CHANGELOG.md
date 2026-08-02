# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Monorepo scopes are inferred from the workspace layout.** `feat: add retry` in a
  forty-package repo is nearly useless; `feat(billing-api): add retry` is not. Each
  staged file is walked up to the nearest directory holding a workspace manifest
  (`package.json`, `pyproject.toml`, `pom.xml`, `go.mod`, `Cargo.toml`, `build.gradle`,
  `composer.json`, `Gemfile`, `mix.exs`, `setup.py`), and when every file lands in the
  same package, its directory name is offered as the Conventional Commits scope. The
  *nearest* manifest wins, so a root `package.json` that only declares `workspaces`
  never beats the package a file actually lives in, and the repository root is never a
  scope — a single-package repo would otherwise get `feat(my-checkout-dir):` on every
  commit. The wrong scope being worse than none, it abstains loudly: files spread
  across sibling packages produce an explicit instruction *not* to pick one and hide
  the rest. It also defers to your history — if the last 200 commits use no scopes at
  all, inference stays silent instead of starting the habit for you, and a scope your
  history has never used is flagged as new. No flag, no configuration, no API call.
- **The message now matches your repository's own house style.** Before writing
  anything, the tool reads the last 200 non-merge commit subjects and bodies with a
  single `git log` and measures what this repo actually does: which Conventional
  Commits types and scopes are in use (and whether prefixes are used at all),
  whether bodies are bulleted, prose or absent, which bullet character, the median
  subject length, which trailers appear, and — when the evidence is unambiguous —
  which human language the subjects are written in. That becomes a ~600-character
  "house style" block at the top of the prompt, so the output stops fighting the
  repo's conventions instead of producing a generic well-formed message. It is
  measured locally on every run, costs no extra API call, and is subtracted from
  the `--max-chars` diff budget rather than added on top of it. Silence is the
  default when the evidence is thin: fewer than five commits produces no block at
  all, and the language is named only when one language both doubles its runner-up
  and is supported by a quarter of the subjects — telling the model a Portuguese
  repo writes Spanish is worse than saying nothing. `--no-house-style` turns the
  whole thing off.
- **A note when a staged file also has unstaged changes.** `git add -p` makes this
  routine and the consequence is easy to miss: the message describes the staged
  version of the code, which is not the version on disk. One line on stderr names the
  files and says so. It informs and never blocks — the staged diff is what is being
  committed, so the message is right; it is the mental model that may be wrong. On
  stderr specifically, so `clerk --dry-run > msg.txt` stays clean.
- **Every staged file is now classified, and the class drives the message.** The
  boolean "is this documentation?" became a taxonomy — `code`, `test`, `docs`,
  `generated`, `config`, `vendor`, `binary` — computed from the path plus the diff's
  own binary markers, sent to the model as an annotation on each filename plus a
  one-line mix (`Class mix: generated 1, test 1, code 2`). The rules now say what to
  do with it: take the type prefix from the classes that are the *point* of the
  commit, and never make a generated, vendored or binary file the subject of the
  message or narrate its contents. So a three-line fix that also regenerates
  `package-lock.json` stops being described as a lockfile change, and a `vendor/`
  bump can no longer masquerade as your own work. `vendor/` wins over every other
  signal, and directory matching is by path segment, so `distance.py` is not mistaken
  for `dist/`.
- **The prompt now includes the structural facts a unified diff leaves out.**
  `git diff --staged --find-renames --stat --summary` goes to the model alongside
  the diff, and the rules tell it what to do with them: a rename is a move and not
  a rewrite, a mode change is a permission change, and a binary file has a size
  change and no readable content to invent. `-M` is passed explicitly, so a repo
  with `diff.renames=false` still gets "rename a => b" rather than a delete plus an
  add. Two things only the summary knows: binary file **sizes**, and mode changes.
  It is capped at 2 000 characters and sits *outside* the `--max-chars` diff budget,
  which is deliberate — when a big commit's diff is trimmed, the summary is the part
  that still describes the whole change.
- **A rejected request parameter now heals itself instead of failing.** Reasoning
  models reject `temperature` outright, and some rename `max_tokens` to
  `max_completion_tokens`. Rather than carry a per-model capability table that rots
  within a quarter, a `400` that names a parameter this tool sent is repaired once —
  the parameter is dropped (if it is an optional sampling knob) or renamed (when the
  provider's own message says *"Use 'x' instead"*) — and the request goes out again.
  This is separate from the transient-failure budget: a permanent error is repaired
  immediately, with no backoff. Required fields are never touched, and `model` in
  particular is protected, because almost every `400` says *"with this model"* and
  would otherwise match it by accident.
- **Transient API failures are retried instead of losing the commit.** A single
  `429` — routine on a free tier — used to throw away the whole message. Rate
  limits, gateway errors and Anthropic's `529` overload now get up to two retries
  with exponential backoff and jitter (so a rate-limited team does not retry in
  lockstep), honouring a numeric `Retry-After` when the server sends one, capped so
  a confused header cannot park a commit for an hour. Every retry is announced on
  stderr, so a slow run explains itself. Deliberately *not* retried: any 4xx that
  is not a rate limit, and a refused connection — retrying a wrong address or a
  local server that is not running just delays the error.
- **`--timeout`**, seconds per API request (default 60). Local models are often
  much slower than a hosted API, and 60 seconds is not always enough.
- **`--provider ollama`: a local model, no API key, nothing over the network.**
  The README's privacy section used to end the conversation with *do not run this
  on repositories whose contents cannot leave your machine*; now it can offer a
  path instead. The preset points at `http://localhost:11434/v1` and requires no
  key — previously the same setup needed both `--base-url` and a placeholder
  `OPENAI_API_KEY=ollama` that meant nothing. Reads `OLLAMA_MODEL` /
  `OLLAMA_BASE_URL`, defaults to `qwen2.5-coder`. Small local models write weaker
  bodies than a hosted model; `-m "<title>"` closes most of that gap.
- **`--provider anthropic`: Claude models via the Anthropic Messages API.** The
  second entry in the provider table, and the one that proves the four-slot shape
  was the right decomposition — all four differ from OpenAI's: `POST /v1/messages`,
  an `x-api-key` plus `anthropic-version` header pair, the system prompt as a
  top-level field with a required `max_tokens`, and a response made of content
  blocks. Reads `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` / `ANTHROPIC_BASE_URL`, and
  defaults to `claude-haiku-4-5` — small and cheap like the OpenAI default, because
  this runs on every commit; `--model claude-opus-5` when a change is subtle. Two
  details worth knowing: the response text is read from the first *text* block
  rather than the first block, so a model that thinks before answering still works,
  and no `temperature` is sent, because current reasoning models reject it.
- **`--base-url` / `$OPENAI_BASE_URL`: any OpenAI-compatible endpoint.** Ollama,
  LM Studio, vLLM, llama.cpp, OpenRouter, Groq, Together, DeepSeek and Azure all
  speak the OpenAI wire format, so one flag reaches all of them with no new code
  and no new dependency — and pointing it at `http://localhost:11434/v1` means the
  staged diff never leaves your machine, which is the honest answer to *"we can't
  send source code to a third party"*. A base URL without a scheme now fails with
  a readable message instead of urllib's "unknown url type", and only `http://`
  and `https://` are accepted. `SECURITY.md` gained a **Where your data goes**
  section spelling out the single request, the destination you control, and the
  cleartext caveat for non-loopback `http://`.
- **`--provider` / `$CLERK_PROVIDER`, and a provider adapter table.** The API
  endpoint, headers, request payload and response extractor are no longer
  hard-wired module constants: they are four slots in a small table, one entry per
  provider, selected at run time. `openai` remains the default and the only entry,
  so nothing changes for existing users — but the key check now belongs to the
  provider rather than to `main()`, which is what a keyless local model needs, and
  `--model` now falls back to the selected provider's default instead of assuming
  OpenAI's. A new **Configuration** section in both READMEs documents the
  environment variables and their precedence.
- **A project website and a logo.** `docs/` now doubles as a self-contained
  GitHub Pages site — <https://alegauss.github.io/commitclerk/> — covering the
  pitch, the documentation-only blind spot, the flag reference, install paths and
  the privacy statement, plus `llms.txt`, `robots.txt` and a sitemap for machine
  readers. The mark (a signed-off commit node beside the message it wrote) ships
  as `docs/logo.svg` with rendered PNGs, and now heads both READMEs.
- **`git clerk` works as a native git subcommand.** Installing now also provides
  a `git-clerk` entry point, which git picks up from `PATH` automatically —
  `git add -A && git clerk` needs no alias and no new command to remember.
  `--help` names whichever entry point you actually invoked.
- `run-commit.sh`, a POSIX wrapper matching `run-commit.cmd`: it checks
  `OPENAI_API_KEY`, stages everything, and forwards its arguments to
  `commitclerk.py`. macOS and Linux users no longer need to hand-roll an alias.

### Changed

- **The source is now a package, and `dist/commitclerk.py` is a build of it.** The
  single file had grown past 1 000 lines, at which point "read the whole thing before
  you trust it" stops being a promise and becomes theatre. The code is now six modules
  with one direction of dependency — `diffing` (pure text shaping), `files`
  (classification and the doc guard), `gitio` (the only module that runs git), `prompt`
  (the rules), `providers` (adapters, retry, repair), `cli` — and
  `scripts/build_single_file.py` concatenates them back into one standalone script with
  no imports beyond the standard library.

  Nothing about the promise changes: the download is still one dependency-free file you
  can audit. What changes is where you get it — `curl` now fetches
  `main/dist/commitclerk.py` — and how it is trusted: CI rebuilds the artifact, **fails
  if it is stale**, and runs the entire test suite a second time against it, so the
  concatenation is proven equivalent rather than assumed. Inside a checkout use
  `python -m commitclerk`; the wrappers add their own directory to `PYTHONPATH`, so a
  copy of `run-commit.sh` next to a downloaded `commitclerk.py` keeps working.
- **Generated and vendored files no longer spend the diff budget.** Their contents
  are replaced by one line — `[... generated file, +300 -300, contents not shown ...]`
  — under the `diff --git` header, so the file is still named and counted but its
  body stops competing with the change the commit is actually about. Measured on a
  real repo: a 300-package `package-lock.json` bump alongside a two-line bug fix went
  from 39 505 characters of diff to 342, with the fix intact instead of sharing the
  budget with a lockfile the model had already been told not to narrate. Demotion
  runs *before* the per-file budget, so the reclaimed space is redistributed to the
  `code` files. Bodies under 500 characters are left alone — a two-line lockfile bump
  is cheaper to send than to explain.
- **An empty model response now fails instead of committing an empty message.**
  Whichever provider is in use, a reply with no message text ends the run with an
  error naming the model, rather than handing `git commit` a blank body.
- **Large diffs are now trimmed per file instead of cut off at the end.**
  `--max-chars` used to chop the diff at N characters, which meant a big commit's
  later files — the ones `git diff` happens to sort last, not the least
  important ones — were invisible to the model, and it wrote a confident message
  about the handful of files it saw. Every changed file now keeps its header and
  a round-robin share of the budget, with a `[... N lines truncated ...]` marker
  where content was dropped. On a real 12-file, 18 KB commit at a 2 000-character
  budget, the old behaviour showed 2 files; the new one shows all 12.

### Fixed

- **A single code file no longer switches the documentation guard off.** This was a
  hole in the project's headline claim: the guard required *every* staged file to be
  documentation, so a 900-line CHANGELOG entry plus a one-line docstring fix went
  back to being described as `feat: implement <the feature the changelog talks
  about>` — the exact lie the tool exists to prevent, in the mixed commit that is far
  more common than the pure one. The guard now has three states, and the mixed one
  names the documentation files, reports documentation's share of the changed lines,
  and tells the model to decide the type prefix **only** from the non-documentation
  diff lines — using `docs:` when those are trivial. Verified against `gpt-4o-mini` on
  exactly that commit: `feat: implement real-time collaboration sync functionality`
  became `docs: update CHANGELOG to document real-time collaboration feature`, while a
  commit that genuinely adds a feature *and* documents it still gets `feat:`. Two
  details earned by that testing: the note is placed **after** the diff (before it,
  48 lines of changelog prose came later and won), and the reported share is capped at
  99%, since a note that says the commit mixes documentation with code should not then
  claim documentation is 100% of it.
- **The wrappers now stage with `git add -A` instead of `git add *`.** The glob
  skipped dot-prefixed paths (`.github/`, `.gitignore`) and never recorded
  deletions, so removing a file could silently be left out of the commit — and
  out of the diff the message was written from.

## [0.2.1] - 2026-07-28

First release published to PyPI. Version `0.2.0` was prepared but never
released — it has no tag and was never uploaded — so its entries are recorded
here, under the version that actually shipped.

### Changed

- **Renamed the project from `ai-commit` to `commitclerk`.** The old name was
  indistinguishable from a dozen other tools in the same niche; the new one says
  what the tool is for — a clerk records what actually changed, and does not
  restate documentation prose as work that was implemented.
- `ai_commit.py` is now `commitclerk.py`, and `run-commit.cmd` calls it under
  the new name.

### Added

- **Installable from PyPI**: `pipx install commitclerk`, providing the `clerk`
  and `commitclerk` commands. Still zero runtime dependencies.
- `--version` flag.
- Automated publishing with PyPI Trusted Publishing (OIDC), no API token in the
  repository. Every *Publish* run picks the next version by itself: it bumps
  `__version__` (patch by default, `minor`/`major` selectable), rolls this
  changelog, commits, tags, uploads and creates the GitHub Release. TestPyPI
  rehearsals build a throwaway `X.Y.Z.devN` version and leave git untouched.
  See `RELEASING.md`.
- `scripts/bump_version.py`, the standard-library helper behind it.
- Project documentation: `README.md` (plus a Brazilian Portuguese translation),
  `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `RELEASING.md` and
  this changelog.
- MIT `LICENSE`.
- GitHub issue templates (bug report, feature request) and a pull request
  template.
- Unit tests covering `_is_doc`, `is_doc_only`, `truncate` and `_system_prompt`.
- CI running the tests, a compile check and `--help` on Python 3.8–3.13 across
  Linux, Windows and macOS, plus a `ruff` lint job.
- Dependabot configuration to keep GitHub Actions up to date.
- `.gitignore`, `.editorconfig` and packaging metadata in `pyproject.toml`.

## [0.1.0] - 2026-07-27

Initial public release.

### Added

- `commitclerk.py`: generates a Conventional Commits message from the staged diff
  via the OpenAI Chat Completions API, prints it, and commits with
  `git commit -F -`.
- `-m/--message` to pin the commit title and have the model write only the body.
- `--dry-run` to print the message without committing.
- `--model` and `$OPENAI_MODEL` to select the model (default `gpt-4o-mini`).
- `--max-chars` to bound how much of the diff is sent (default 60 000).
- Documentation-only detection: commits touching only `.md`, `.mdx`, `.rst`,
  `.txt`, `.adoc`, anything under `docs/`, or known doc filenames get a `docs:`
  prefix and a framing that describes the documentation change itself rather
  than restating features that shipped in earlier commits.
- `run-commit.cmd`: Windows wrapper that verifies `OPENAI_API_KEY`, stages
  everything, and forwards its arguments to `commitclerk.py`.

[Unreleased]: https://github.com/alegauss/commitclerk/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/alegauss/commitclerk/releases/tag/v0.2.1
[0.1.0]: https://github.com/alegauss/commitclerk/commit/6f72451
