# Security Policy

## Supported versions

`commitclerk` is a single script distributed from the `main` branch. Only the
latest commit on `main` is supported — please verify a problem still reproduces
there before reporting it.

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

Report it privately through GitHub Security Advisories:

👉 **[Report a vulnerability](https://github.com/alegauss/commitclerk/security/advisories/new)**

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
- Leakage of an API key (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) to disk, logs,
  process arguments, or any destination other than the configured API endpoint
- Sending repository content anywhere other than the configured API endpoint
- Anything that causes an unintended, destructive git operation

## Where your data goes

`commitclerk` makes exactly **one** network request per run: an HTTPS POST of the
prompt (the staged diff, the staged file list, the rules, and a measured summary
of your recent commit *messages*) to the endpoint you configured. Nothing else is
transmitted — no telemetry, no analytics, no remote config, no second call.

The commit-message summary is the "house style" block: `commitclerk` reads the
subjects and bodies of the last 200 non-merge commits locally and sends only
**counts and shapes** derived from them — the types and scopes in use, the body
shape, the median subject length, the trailer keys, the language. No commit
message text is transmitted, with one exception: **scope names** (the `api` in
`feat(api):`) and **trailer keys** (`Refs`) appear verbatim, because a count of
them would be useless. No diff, patch, author, email, date or SHA from history is
read or sent. `--no-house-style` skips the `git log` entirely.

That endpoint is `https://api.openai.com/v1/chat/completions` by default, and it
is under your control:

| What you set | Effect |
|---|---|
| nothing | The default OpenAI endpoint, `https://api.openai.com/v1/chat/completions`. |
| `--provider anthropic` | Anthropic's Messages API, `https://api.anthropic.com/v1/messages`, authenticated with `ANTHROPIC_API_KEY`. |
| `--provider ollama` | A local server at `http://localhost:11434/v1`, with **no API key** and nothing sent over the network. |
| `--base-url` / a provider's base-url variable | The diff goes to **that** host instead — including any other `http://localhost:...` server, in which case nothing leaves the machine. |

Two consequences worth being explicit about: a custom base URL is a deliberate
change of destination for your source code, so point it only at a host you trust;
and because a plain `http://` URL is accepted (local servers rarely have TLS), a
non-loopback `http://` endpoint sends your diff over the network in the clear.
Only `http://` and `https://` are accepted at all — anything else is rejected
before the request is built.

## What is out of scope

- **The staged diff, and the house-style summary of past commit messages, being
  sent to the configured API endpoint.** This is the
  documented, intentional behavior of the tool — see
  [Privacy and cost](README.md#privacy-and-cost). Do not use `commitclerk` on
  repositories whose contents may not leave your machine, unless you are running a
  local model (`--provider ollama`, or `--base-url` pointed at your own server).
- **`run-commit.cmd` / `run-commit.sh` staging every change with `git add -A`.**
  This is documented behavior of the wrappers. Stage manually and call
  `commitclerk.py` directly if you need control over what is committed.
- Vulnerabilities in a provider's API (OpenAI, Anthropic), in `git`, or in CPython
  itself — report those to their respective maintainers.
- The quality or accuracy of generated commit messages. That is a bug report,
  not a security issue.

## Handling your API key

- `commitclerk` reads the selected provider's key (`OPENAI_API_KEY` or
  `ANTHROPIC_API_KEY`) from the environment only. It is never written to a file,
  never printed, and never passed as a command-line argument. Only the selected
  provider's key is read — choosing one provider does not touch the other's key.
- The key is sent to whatever `--base-url` names. Do not pair a real OpenAI key
  with a third-party base URL you do not trust — use a key issued by that host.
- Never paste a key into an issue, pull request, or discussion. If you do,
  [revoke it immediately](https://platform.openai.com/api-keys).
- Prefer a key scoped to the minimum permissions your workflow needs, and rotate
  it periodically.
