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
prompt (the staged diff, the staged file list, the rules, a measured summary of
your recent commit *messages*, and two or three past commit messages as style
examples) to the endpoint you configured. Nothing else is transmitted — no
telemetry, no analytics, no remote config, no second call.

**`--deep` is the one exception to "exactly one request", and it is opt-in.**
When it is on (by flag, or `"deep": true` in a config file), every file too large
for the `--max-chars` budget is first sent on its own, to the **same** endpoint
with the same key, to be summarised in two lines. Two things change: there are
now N+1 requests rather than one, and each of those N carries that file's diff
**in full** (up to 60 000 characters) instead of the smaller share the budget
would have trimmed it to — so a run with `--deep` sends *more* of your code than
the same run without it. No new destination, no new file read, and nothing extra
happens at all when the staged diff already fits the budget. It is off by default
for this reason.

`commitclerk` reads the subjects, bodies and touched file paths of the last 200
non-merge commits locally, with one `git log`, and uses them in two ways:

- **The "house style" block** sends only **counts and shapes** derived from them —
  the types and scopes in use, the body shape, the median subject length, the
  trailer keys, the language. No message text, with one exception: **scope names**
  (the `api` in `feat(api):`) and **trailer keys** (`Refs`) appear verbatim,
  because a count of them would be useless.
- **Worked examples** are the exception to that rule and the one place past commit
  message **text is transmitted verbatim**: the two or three commits whose touched
  paths overlap your staged diff most are included as few-shot examples, subject
  plus body, each body clipped to 400 characters. Trailer blocks are stripped
  first, so `Co-authored-by:` lines and the email addresses in them are not sent.

No diff, patch, author, email, date or SHA from history is read or sent. Those
are two different data flows, so there are two switches: **`--no-examples`**
(or `"examples": false`) is the one to use if past commit message text must not
leave the machine — it keeps the fingerprint, which is counts and shapes — and
**`--no-house-style`** (or `"house_style": false`) skips the `git log` entirely
and refuses both, which is also what makes `"examples": true` under
`"house_style": false` mean nothing: there is no history to draw from.

When ticket trailers are enabled, the **current branch name** is read as well
(`git rev-parse --abbrev-ref HEAD`) and matched against a regular expression. It
is **not** sent to the model: the matched key is appended to the finished message
locally, so the branch name never appears in the request. With the feature off,
which is the default, the branch is not read at all.

Scope inference is the only part of the tool that touches files outside the staged
diff, and it never **reads** one: it asks whether a manifest (`package.json`,
`pyproject.toml`, `go.mod`, …) *exists* in each ancestor directory of a staged
file, and transmits at most the resulting directory name — which is already part
of the staged path the model receives. No manifest contents are opened or sent.

That endpoint is `https://api.openai.com/v1/chat/completions` by default, and it
is under your control:

| What you set | Effect |
|---|---|
| nothing | The default OpenAI endpoint, `https://api.openai.com/v1/chat/completions`. |
| `--provider anthropic` | Anthropic's Messages API, `https://api.anthropic.com/v1/messages`, authenticated with `ANTHROPIC_API_KEY`. |
| `--provider ollama` | A local server at `http://localhost:11434/v1`, with **no API key** and nothing sent over the network. |
| `--base-url` / a provider's base-url variable | The diff goes to **that** host instead — including any other `http://localhost:...` server, in which case nothing leaves the machine. |
| `provider` or `base_url` in a config file | The same effect, from `.clerk.json` at the repository root or `~/.config/clerk/config.json`. A flag and the environment both override it. |

Three consequences worth being explicit about. A custom base URL is a deliberate
change of destination for your source code, so point it only at a host you trust.
Because a plain `http://` URL is accepted (local servers rarely have TLS), a
non-loopback `http://` endpoint sends your diff over the network in the clear;
only `http://` and `https://` are accepted at all — anything else is rejected
before the request is built. And **`.clerk.json` is a file the repository can
carry**: cloning a repository and running `commitclerk` in it lets that repository
choose the endpoint your diff is sent to. It is plain JSON at the top level, meant
to be reviewed like any other file you run code from, and `--base-url` or the
environment overrides it — but read it first in a repository you did not write.

One file's contents *are* sent when it exists: `.clerk/context.md` at the
repository root, the standing note the author wrote for the model. It is read
verbatim, truncated at 2 000 characters, and included in the prompt — which is
the entire point of it, and the reason not to put anything in it you would not
send to your provider. `--context "<note>"` is the same channel, typed once. With
neither, nothing extra is read or sent.

## The config files

`commitclerk` reads two files, both optional, both plain JSON, and neither ever
written by the tool:

- `.clerk.json` at the repository root (`git rev-parse --show-toplevel`)
- `~/.config/clerk/config.json`

Only ten keys are recognised — `provider`, `model`, `base_url`, `timeout`,
`max_chars`, `house_style`, `examples`, `deep`, `ticket_refs`, `ticket_pattern` —
and each is type-checked before it takes effect; a
key that is not one of those is reported on stderr and ignored. **API keys are
not settings and are never read from either file**, so a config file committed to
a repository cannot carry, capture or redirect a credential. Nothing from these
files is transmitted: they only choose what the tool does with the request it was
already going to make — though `base_url` chooses **where** it is made, and
`deep` chooses **how many** requests it becomes and how much of each large file
goes into them.

## What is out of scope

- **The staged diff, the house-style summary of past commit messages, the past
  commit messages used as style examples, and — with `--deep` — the full diff of
  each oversized file, being sent to the configured API endpoint.** This is the
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
