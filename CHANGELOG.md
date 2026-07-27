# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Project documentation: `README.md` (plus a Brazilian Portuguese translation),
  `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md` and this changelog.
- MIT `LICENSE`.
- GitHub issue templates (bug report, feature request, question) and a pull
  request template.
- CI workflow running `ruff` and a compile/CLI smoke check on Python 3.8–3.13.
- Dependabot configuration to keep GitHub Actions up to date.
- `.gitignore` and `.editorconfig`.

## [0.1.0] - 2026-07-27

Initial public release.

### Added

- `ai_commit.py`: generates a Conventional Commits message from the staged diff
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
  everything, and forwards its arguments to `ai_commit.py`.

[Unreleased]: https://github.com/alegauss/ai-commit/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/alegauss/ai-commit/releases/tag/v0.1.0
