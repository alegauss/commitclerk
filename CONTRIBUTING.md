# Contributing to commitclerk

Thanks for taking the time to help. This is a small project with a deliberately
small surface, so the rules are short.

## Design principles

Please respect these — a PR that breaks one will be asked to change, no matter
how good the feature is.

1. **Zero third-party dependencies.** Standard library only. If a feature needs
   `requests`, it needs `urllib` instead. No `requirements.txt`, no lockfile.
2. **One file, still.** The source is the `commitclerk/` package, but
   `dist/commitclerk.py` is a build of that package into a single standalone script,
   and someone must always be able to `curl` it into a repo and have it work. So:
   standard-library imports only, no new top-level module outside the package, and
   **run `python scripts/build_single_file.py` in the same commit as any source
   change** — CI fails if the artifact is stale, and runs the whole test suite
   against it as well as against the package.
3. **Never surprise the user's history.** The tool prints the message before
   committing and never stages, amends, rebases, or pushes anything by itself.
4. **Nothing leaves the machine except the staged diff.** No telemetry, no
   analytics, no remote configuration.
5. **Readable over clever.** People fork this file to adapt it to their team's
   conventions. Optimize for the person reading it six months from now.

## Getting set up

```bash
git clone https://github.com/alegauss/commitclerk.git
cd commitclerk
export OPENAI_API_KEY="sk-..."
```

There is nothing to install. Python 3.8+ and `git` are the only requirements.

## Making a change

1. **Open an issue first** for anything beyond a typo or an obvious bug fix.
   It's cheaper to agree on the approach before the code exists.
2. Create a branch: `git checkout -b feat/short-description`.
3. Make the change.
4. Test it (see below).
5. Commit — using `commitclerk` itself, ideally:
   `python -m commitclerk -m "feat: your title"`.
6. Open a pull request and fill in the template.

## Testing your change

Run the unit tests — standard library `unittest`, nothing to install:

```bash
python -m unittest discover -s tests -v
```

They cover the pure functions (`_is_doc`, `is_doc_only`, `truncate`,
`_system_prompt`) and never hit the network. Please add a case when you change
one of them.

Then verify by hand before opening a PR:

```bash
# Rebuild the single-file artifact (do this before committing)
python scripts/build_single_file.py

# The CLI still parses, both ways
python -m commitclerk --help
python dist/commitclerk.py --help

# It still compiles on the versions CI checks
python -m compileall -q commitclerk dist/commitclerk.py

# The suite passes against the artifact too, not just the package
COMMITCLERK_SOURCE=dist python -m unittest discover -s tests

# A real end-to-end run that commits nothing
git add <some files>
python -m commitclerk --dry-run
python -m commitclerk --dry-run -m "chore: manual check"

# Documentation-only detection still fires
git add README.md
python -m commitclerk --dry-run     # must produce a docs: title
```

If your change touches `_is_doc` / `is_doc_only`, exercise both branches: a
docs-only staged set and a mixed code+docs set.

CI runs the tests, a compile check and a `--help` smoke test on Python
3.8–3.13 (Linux, Windows and macOS), plus `ruff`. Run `ruff check .` locally if
you have it — the configuration lives in `pyproject.toml`.

## Changing the prompt

The prompt rules in `_RULES`, `_DOC_ONLY_NOTE`, and `_system_prompt()` are the
heart of the tool. When you propose a change to them:

- Explain **what bad output you observed** and on what kind of diff.
- Include a before/after example of the generated message in the PR body.
- Keep the rules short. Long prompts dilute every individual instruction.

## Commit and PR conventions

- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `build:`, `perf:`.
- Keep PRs focused on one thing. Two unrelated fixes are two PRs.
- Update `README.md` when you change a flag, an environment variable, or the
  default behavior.
- Add an entry to `CHANGELOG.md` under `## [Unreleased]`.

## Reporting bugs

Open an [issue](https://github.com/alegauss/commitclerk/issues/new/choose) with
the bug report template. Include your Python version, OS, the exact command you
ran, and — if the problem is a bad commit message — the message you got and the
one you expected.

**Never paste your API key, and redact anything sensitive from diffs you share.**

## Releasing

Maintainers only — the process is documented in [RELEASING.md](RELEASING.md).
Releases are published to PyPI automatically from a GitHub Release using
Trusted Publishing; there are no API tokens in this repository.

## Security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md).

## Code of Conduct

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
