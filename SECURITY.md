# Security Policy

## Supported versions

`ai-commit` is a single script distributed from the `main` branch. Only the
latest commit on `main` is supported — please verify a problem still reproduces
there before reporting it.

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

Report it privately through GitHub Security Advisories:

👉 **[Report a vulnerability](https://github.com/alegauss/ai-commit/security/advisories/new)**

Please include:

- A description of the issue and its impact
- Steps to reproduce, or a proof of concept
- The commit SHA you tested against, plus your OS and Python version

You can expect an acknowledgement within **7 days** and a status update within
**30 days**. This is a volunteer-maintained project, so please be patient — and
credit will be given in the advisory unless you prefer to stay anonymous.

## What is in scope

- Command injection or arbitrary code execution through crafted repository
  contents, filenames, branch names, or CLI arguments
- Leakage of the `OPENAI_API_KEY` to disk, logs, process arguments, or any
  destination other than the OpenAI API
- Sending repository content anywhere other than the configured API endpoint
- Anything that causes an unintended, destructive git operation

## What is out of scope

- **The staged diff being sent to the OpenAI API.** This is the documented,
  intentional behavior of the tool — see [Privacy and cost](README.md#privacy-and-cost).
  Do not use `ai-commit` on repositories whose contents may not leave your
  machine.
- **`run-commit.cmd` staging every change with `git add *`.** This is documented
  behavior of the wrapper. Stage manually and call `ai_commit.py` directly if
  you need control over what is committed.
- Vulnerabilities in OpenAI's API, in `git`, or in CPython itself — report those
  to their respective maintainers.
- The quality or accuracy of generated commit messages. That is a bug report,
  not a security issue.

## Handling your API key

- `ai-commit` reads `OPENAI_API_KEY` from the environment only. It is never
  written to a file, never printed, and never passed as a command-line argument.
- Never paste a key into an issue, pull request, or discussion. If you do,
  [revoke it immediately](https://platform.openai.com/api-keys).
- Prefer a key scoped to the minimum permissions your workflow needs, and rotate
  it periodically.
