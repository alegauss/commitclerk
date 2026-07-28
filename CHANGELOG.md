# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

- **Large diffs are now trimmed per file instead of cut off at the end.**
  `--max-chars` used to chop the diff at N characters, which meant a big commit's
  later files — the ones `git diff` happens to sort last, not the least
  important ones — were invisible to the model, and it wrote a confident message
  about the handful of files it saw. Every changed file now keeps its header and
  a round-robin share of the budget, with a `[... N lines truncated ...]` marker
  where content was dropped. On a real 12-file, 18 KB commit at a 2 000-character
  budget, the old behaviour showed 2 files; the new one shows all 12.

### Fixed

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
