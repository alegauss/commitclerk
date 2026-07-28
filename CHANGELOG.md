# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-07-28

### Added

- The *Publish* workflow now picks the next version by itself: a run bumps
  `__version__` (patch by default, `minor`/`major` selectable), rolls the
  changelog, commits, tags, publishes and creates the GitHub Release. TestPyPI
  rehearsals build a throwaway `X.Y.Z.devN` version and leave git untouched.
- `scripts/bump_version.py`, the standard-library helper behind it.

## [0.2.0] - 2026-07-27

First release published to PyPI.

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
- Automated publishing via GitHub Releases using PyPI Trusted Publishing (OIDC),
  with a manual TestPyPI rehearsal path — see `RELEASING.md`.
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
[0.2.1]: https://github.com/alegauss/commitclerk/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/alegauss/commitclerk/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/alegauss/commitclerk/releases/tag/v0.1.0
