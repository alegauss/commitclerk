# Contributing to ai-commit

Thanks for taking the time to help. This is a small project with a deliberately
small surface, so the rules are short.

## Design principles

Please respect these — a PR that breaks one will be asked to change, no matter
how good the feature is.

1. **Zero third-party dependencies.** Standard library only. If a feature needs
   `requests`, it needs `urllib` instead. No `requirements.txt`, no lockfile,
   no build step.
2. **One file.** `ai_commit.py` stays self-contained and copy-pasteable. Someone
   should be able to `curl` it into a repo and have it work.
3. **Never surprise the user's history.** The tool prints the message before
   committing and never stages, amends, rebases, or pushes anything by itself.
4. **Nothing leaves the machine except the staged diff.** No telemetry, no
   analytics, no remote configuration.
5. **Readable over clever.** People fork this file to adapt it to their team's
   conventions. Optimize for the person reading it six months from now.

## Getting set up

```bash
git clone https://github.com/alegauss/ai-commit.git
cd ai-commit
export OPENAI_API_KEY="sk-..."
```

There is nothing to install. Python 3.8+ and `git` are the only requirements.

## Making a change

1. **Open an issue first** for anything beyond a typo or an obvious bug fix.
   It's cheaper to agree on the approach before the code exists.
2. Create a branch: `git checkout -b feat/short-description`.
3. Make the change.
4. Test it (see below).
5. Commit — using `ai-commit` itself, ideally:
   `python ai_commit.py -m "feat: your title"`.
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
# The CLI still parses
python ai_commit.py --help

# It still compiles on the versions CI checks
python -m compileall -q ai_commit.py

# A real end-to-end run that commits nothing
git add <some files>
python ai_commit.py --dry-run
python ai_commit.py --dry-run -m "chore: manual check"

# Documentation-only detection still fires
git add README.md
python ai_commit.py --dry-run     # must produce a docs: title
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

Open an [issue](https://github.com/alegauss/ai-commit/issues/new/choose) with
the bug report template. Include your Python version, OS, the exact command you
ran, and — if the problem is a bad commit message — the message you got and the
one you expected.

**Never paste your API key, and redact anything sensitive from diffs you share.**

## Security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md).

## Code of Conduct

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
