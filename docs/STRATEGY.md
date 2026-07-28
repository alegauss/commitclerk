# commitclerk — Strategy

Positioning, audience, distribution and licensing decisions. **Not a backlog** —
nothing here gets a `T<n>`. When a decision here implies work, that work becomes a
task in [`ROADMAP.md`](ROADMAP.md) with the rationale in
[`IMPROVEMENTS.md`](IMPROVEMENTS.md).

---

## What this is

A single-file, zero-dependency CLI that writes a Conventional Commits message from
your staged diff — and, uniquely in its category, **refuses to describe
documentation prose as work that was implemented**.

## The one-sentence differentiator

Every competitor reads the diff. commitclerk reads the diff **and knows what kind
of change it is looking at** — which is why a CHANGELOG edit describing a feature
that shipped last week does not become `feat: implement <feature>` in your history.

That is the whole wedge, and every roadmap block is either deepening it (Blocks B
and C: more context, better classification) or removing a reason not to adopt it
(Blocks A, D, E, F, G).

## Who it is for

| Segment | What they need | Where the roadmap serves them |
| --- | --- | --- |
| **Individual developers** | Install in 30 seconds, no config, sane defaults | Already served; T49 (demo GIF) and T46 (Homebrew/Scoop) are about them finding it |
| **Small teams with a convention** | Encode the convention once, enforce it | Block E (config, rule packs, `--lint`) |
| **Privacy-constrained orgs** | The diff must not reach a third party | T4 (local models), T19/T20 (secret scan, `.clerkignore`), T24 (threat model) |
| **Monorepo / platform teams** | Correct scopes, huge diffs handled honestly | T10 (scope inference), Block C |
| **Non-English teams** | History in their working language | T27, and T7 detecting it from history |
| **Maintainers of released software** | Changelogs and release notes, not just commits | Block H |

The individual developer is the acquisition channel; the team is where the tool
becomes load-bearing. Features that only serve teams still need to be free and
frictionless for the individual, because the individual is who installs it first.

## Competitive position

The category (`aicommits`, `opencommit`, `gitmoji`-flavoured variants, IDE
built-ins) is crowded, mature and mostly Node-based. Competing on "generates a
commit message with an LLM" is competing on nothing. The defensible ground:

1. **Auditability.** One file, standard library only, readable end to end. In a
   category where the tool sees all your source code, "you can read it before you
   trust it" is a *security* argument, not an aesthetic one. This is why the
   zero-dependency rule is a non-goal violation and not a preference.
2. **Correctness about intent.** The doc-only guard, and its generalisations in
   Blocks B and C. Nobody else treats "the diff misleads" as a first-class problem.
3. **Being useful without the LLM.** `--lint` (T28) and `--offline` (T21) mean the
   tool has value for people who will never send a diff anywhere. No competitor
   ships a useful no-API-call mode.
4. **Documenting the threat model.** Prompt injection from diff content (§D.1) is
   real and unaddressed across the category. Being first to write it down is
   cheap credibility.

**Where not to compete:** IDE plugins, a GUI, a hosted service, model hosting, or
"AI pair programmer" scope creep. Every one of those trades the auditability
argument for a feature someone else already does better.

## Distribution bets

- **PyPI is the base**, already shipping with Trusted Publishing and automated
  version bumps.
- **The `curl` single-file path is a genuine differentiator** and should be
  protected: it must keep working forever, including after the eventual package
  split (§J.5 requires the build to emit a concatenated single file). Publishing a
  SHA-256 with each release (T46) makes it defensible rather than merely
  convenient.
- **Homebrew and Scoop** because commit messages are not a Python-specific
  concern and `pipx` is a Python-developer habit.
- **The GitHub Action (T45) is marketing that also works** — it shows output to
  people who have installed nothing.
- **No package for npm.** Wrapping a Python tool in a Node package to reach Node
  developers is how a zero-dependency tool acquires a dependency tree and a second
  maintenance burden. Homebrew is the right answer for that audience.

## Licensing and monetisation

**MIT, permanently. No paid tier, no open-core, no hosted plan.** A tool whose
entire value proposition is "small enough that you can audit it" cannot have a
withheld feature set without undermining itself. If the project ever needs
funding, sponsorship is the only route consistent with the pitch.

Practical consequence for the roadmap: no task may assume a licence server, a
registration step, an account, or a feature flag keyed to anything but local
configuration.

## Naming

The rename from `ai-commit` to `commitclerk` (v0.2.1) is settled and should not be
relitigated. `ai-commit` was indistinguishable from a dozen neighbours and dated
itself to a moment when "AI" was the differentiator. *A clerk records what actually
happened* — which is precisely the doc-only insight in two words.

Binary names: `clerk` (primary, short, the one to teach), `commitclerk` (explicit,
collision-safe), and eventually `git-clerk` (T37) so `git clerk` works. Keep all
three; the cost is three lines of packaging metadata.

## Compatibility policy

- **Python 3.8** is the floor while it remains in the CI matrix. It is the reason
  configuration is JSON rather than TOML (§E.1). Raising the floor is a
  `STRATEGY.md` decision, not an implementation convenience — revisit when 3.8 and
  3.9 are both long past end of life, and treat 3.11 (for `tomllib`) as the next
  meaningful step rather than "latest".
- **Semantic versioning**, with the CLI surface — flag names, exit codes, config
  keys, output shape under `--dry-run` — as the public API. Piping `--dry-run` into
  another script is a supported use, so changing that output is a breaking change.
- **Deprecations get one minor release of warning** before removal, and a
  `CHANGELOG.md` `Deprecated` entry at the moment the warning appears, not at
  removal.

## Deprecation watchlist

- **`run-commit.cmd` at the repo root.** It is a personal wrapper that predates
  the PyPI package, it is Windows-only, and it stages with a buggy `git add *`
  (§G.3). Once T36 (hook) and T38 (POSIX wrapper, with `git add -A`) land, it is a
  documented convenience at best. Fix the staging bug first regardless; retire it
  only when the hook is genuinely better.
- **`--max-chars` as the only budget control.** Superseded by the per-file budget
  (T13). Keep the flag as the total budget so nobody's script breaks; the change
  is in how the budget is *spent*, which is not a breaking change.
- **`gpt-4o-mini` as the hardcoded default.** A default model name is a
  perishable good. Once the provider table exists (T1), the default belongs in one
  clearly-marked constant with a comment about when it was last reviewed, and the
  README should stop implying the tool is OpenAI-shaped.

## How to say no

The fastest way to ruin this project is a stream of individually reasonable
features. Three tests, in order, before anything becomes a task:

1. **Does it need a dependency?** Then it is not this tool.
2. **Does it make the single file unreadable?** Then it waits for §J.5, or it
   doesn't happen.
3. **Would a user who only wants a commit message notice it?** If yes, it must be
   off by default.

Everything in the current roadmap passes all three. Anything that doesn't belongs
in an issue thread, not in `ROADMAP.md`.
