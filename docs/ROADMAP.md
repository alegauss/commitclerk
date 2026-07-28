# commitclerk — Roadmap

The **only** source of truth for what is planned and what is active. Shipped work
lives in [`CHANGELOG.md`](../CHANGELOG.md); design rationale for the tasks below
lives in [`IMPROVEMENTS.md`](IMPROVEMENTS.md); positioning and distribution bets
live in [`STRATEGY.md`](STRATEGY.md). Maintenance rules:
[`.claude/skills/commitclerk-roadmap-docs`](../.claude/skills/commitclerk-roadmap-docs/SKILL.md).

**Status legend:** 💭 idea · 📋 designed · 🛠 in-progress · ⏳ partial.
Shipped tasks are *removed* from this file — they are not marked ✅ here.

**Next free task number and block letter:** [`last-task.md`](last-task.md).

---

## The thesis

commitclerk today is a very good ~460-line script with one genuinely differentiated
idea: **it refuses to describe documentation prose as work that was implemented.**
Everything below is an answer to one of three questions:

1. **Will it scale technically?** The tool knows nothing about the repo beyond the
   staged diff, and one transient 429 still loses a commit. Blocks **A**, **B** and
   **C** fix the ceiling.
2. **Can a team actually adopt it?** A tool that ships a raw diff to a third party
   with no redaction, no config file, no offline path and no `commit-msg`
   validation cannot be mandated by anyone. Blocks **D**, **E**, **F** and **G**
   make it adoptable rather than merely installable.
3. **Is a commit message the whole product?** The same staged-diff-plus-history
   pipeline can write changelogs, release notes, PR descriptions and a semver
   recommendation. Block **H** is where the tool stops being a one-trick script.
   Blocks **I** and **J** are reach and the ability to change the prompt without
   silently breaking it.

## Non-goals (binding — check before proposing work)

- **No runtime dependencies in the core path.** Standard library only. This is the
  product's trust story, not a preference. A task that needs a package is a task
  that needs a redesign, or a `STRATEGY.md` decision first.
- **No telemetry, analytics, remote config, or phone-home.** Ever. Not opt-in.
- **No hosted service and no server component.** The tool runs on your machine.
- **Never stage silently from the Python entrypoint.** Wrappers may stage; the
  tool itself reads what you chose to stage. Losing this makes the tool unsafe to
  put behind a hook.
- **No auto-push, no auto-PR, no auto-merge.** The commit is the last step.
- **Not a code reviewer or a linter for code.** It describes changes; it does not
  judge them.
- **No gitmoji / emoji in messages by default**, and no "written by AI" watermark
  by default (see T23 for the opt-in trailer).
- **Do not rewrite history.** No amend-by-default, no interactive rebase driving.
- **Not a fork-per-team product.** Conventions are configuration (Block E), not
  patches to `_RULES`.

---

## Block A — Provider portability

*OpenAI, Anthropic, a keyless local preset and any OpenAI-compatible endpoint all
work. What is left is not losing a commit to a transient failure.* → [§A](IMPROVEMENTS.md#a--provider-portability)

| ID | Status | Task | Depends on |
| --- | --- | --- | --- |
| T5 | 💭 | Retry with exponential backoff + jitter on 429/5xx, plus `--timeout`. One transient 429 currently loses the whole commit. → §A.4 | — |
| T6 | 💭 | Capability fallback: if a model rejects `temperature` or the parameter name differs (reasoning models), retry once without it instead of dying with a raw API error. → §A.4 | T5 |

## Block B — Context beyond the diff

*The tool's founding insight is that the diff alone misleads. That insight is
under-exploited: the repository is full of cheap, local, zero-cost context.* → [§B](IMPROVEMENTS.md#b--context-beyond-the-diff)

| ID | Status | Task | Depends on |
| --- | --- | --- | --- |
| T7 | 💭 | **House-style fingerprint** — sample the last N commit subjects, derive the types and scopes this repo actually uses, its body style (bullets? paragraphs? none?), and its language, then inject a compact "house style" block. Makes output match *this* repo instead of a generic ideal. → §B.1 | — |
| T8 | 💭 | **Few-shot from your own history** — pick the 2–3 past commits whose touched paths overlap the current diff most and include their title+body as examples. Local, free, no telemetry, and it improves with the repo's age. → §B.1 | T7 |
| T9 | 💭 | Branch/ticket context: parse an issue key out of the branch name (`feat/PROJ-123-thing`) via a configurable regex and emit a `Refs: PROJ-123` trailer. → §B.2 | T25 |
| T10 | 💭 | Monorepo scope inference: derive the Conventional Commits scope from the common path prefix or the nearest workspace manifest (`package.json`, `pyproject.toml`, `pom.xml`, `go.mod`). → §B.3 | — |
| T11 | 💭 | Feed the facts a unified diff hides: renames, mode/permission changes, pure deletions, binary blobs, submodule bumps. Today a rename reads as a giant delete+add. → §B.4 | — |
| T12 | 💭 | `--context "<note>"` for one-off intent, plus `.clerk/context.md` for standing repo facts ("this repo ships a CLI; `clerk` is the binary name"). → §B.5 | T25 |

## Block C — Diff intelligence

*A 60 000-character head-cut is the crudest possible answer to a large diff: the
last file changed is simply invisible to the model.* → [§C](IMPROVEMENTS.md#c--diff-intelligence)

| ID | Status | Task | Depends on |
| --- | --- | --- | --- |
| T14 | 💭 | **File-class taxonomy** — `code · test · docs · generated · config · vendor · binary` — replacing the boolean doc-only flag. The class mix is summarized in the prompt and drives the type prefix. → §C.2 | — |
| T15 | 💭 | Demote generated files (lockfiles, snapshots, `dist/`, `*.min.*`, migrations, `.po`) to a one-line "N generated files changed" instead of thousands of diff lines competing for the budget. → §C.2 | T14 |
| T16 | 💭 | **Mixed doc+code commits**: today one code file disables the doc guard entirely, so a 900-line CHANGELOG edit plus a typo fix can still produce `feat:`. Make the guard per-file rather than all-or-nothing. → §C.3 | T14 |
| T17 | 💭 | Map-reduce pass for very large diffs (opt-in): summarize each oversized file separately, then write the message from the summaries. Handles the commit that no budget can fit. → §C.4 | — |
| T18 | 💭 | Warn when the same files have *unstaged* changes too — the message may describe a version of the code that is not the one being committed. → §C.5 | — |

## Block D — Trust & safety

*This block is what turns "a neat script" into "a tool a company can approve".* → [§D](IMPROVEMENTS.md#d--trust--safety)

| ID | Status | Task | Depends on |
| --- | --- | --- | --- |
| T19 | 💭 | **Secret pre-flight** — scan the staged diff for known key shapes and high-entropy strings *before* the request leaves the machine; refuse by default, `--redact` to mask and continue, `--no-scan` to override. A committed secret sent to a third-party API is the worst thing this tool could do. → §D.1 | — |
| T20 | 💭 | `.clerkignore`: paths whose contents are never transmitted, replaced by a filename-and-linecount placeholder. Lets a team allow the tool on a repo with a few sensitive files. → §D.2 | — |
| T21 | 💭 | `--offline`: a deterministic, LLM-free message (type from file classes, scope from paths, bullets grouped by directory). No key, no network, no failure mode — so a hook or CI job can never hard-block a commit. → §D.3 | T14 |
| T22 | 💭 | CI job that runs the suite with socket creation monkeypatched to raise, proving there is no accidental egress path outside the one documented call. → §D.4 | T53 |
| T23 | 💭 | Opt-in `Assisted-by: commitclerk <version> (<model>)` trailer for teams that need AI-assistance provenance in history. Off by default. → §D.5 | T25 |
| T24 | 💭 | A real data-flow / threat-model section in `SECURITY.md`: exactly what leaves the machine, what never does, what an attacker controlling the model output could attempt (prompt injection *from diff content* into the commit message is a genuine vector). → §D.1 | T19 |

## Block E — Configuration & conventions

*Every team's commit convention is slightly different. Today the only way to encode
that is to fork `_RULES`, which is how a tool acquires a thousand incompatible
forks and no ecosystem.* → [§E](IMPROVEMENTS.md#e--configuration--conventions)

| ID | Status | Task | Depends on |
| --- | --- | --- | --- |
| T25 | 💭 | `.clerk.json` project config (types, scopes, title length, language, ticket regex, model, provider) with documented precedence **CLI > env > project > user > default**. JSON, not TOML — `tomllib` is 3.11+ and the floor is 3.8. → §E.1 | — |
| T26 | 💭 | Rule packs: `--rules <file>` / `$CLERK_RULES` to replace or append to `_RULES`, so a team encodes its convention without forking the tool. → §E.2 | T25 |
| T27 | 💭 | `--lang pt-BR` (and friends) so the message matches the team's working language. The project already ships a pt-BR README; the tool should be able to speak it. → §E.3 | T25 |
| T28 | 💭 | **`clerk --lint`** — validate an existing message (a file, or `HEAD`) against the same rules with **zero API calls**. Turns a one-way generator into a two-sided tool: usable as a `commit-msg` hook and in CI, by people who don't want generation at all. → §E.4 | T25 |
| T29 | 💭 | Enforce the configured type/scope allowlist on the model's output: one repair retry, then fail loudly rather than committing an off-convention message. → §E.4 | T28 |

## Block F — Interaction & UX

*The current flow is fire-and-commit: if the message is wrong, your only recourse
is `git commit --amend`.* → [§F](IMPROVEMENTS.md#f--interaction--ux)

| ID | Status | Task | Depends on |
| --- | --- | --- | --- |
| T30 | 💭 | Interactive confirm loop — `[a]ccept · [e]dit · [r]egenerate · [q]uit` — with `--yes` to keep the current non-interactive behaviour for scripts. → §F.1 | — |
| T31 | 💭 | `--edit`: open the generated message in `$EDITOR` / `core.editor` before committing. → §F.1 | T30 |
| T32 | 💭 | Stream the completion so a slow or local model shows progress instead of a frozen terminal for 30 seconds. → §F.2 | — |
| T33 | 💭 | `--verbose`: model, prompt/completion tokens, estimated cost, elapsed time, prompt version. `--quiet` for hook use. Cost is currently invisible. → §F.3 | T52 |
| T34 | 💭 | `--amend`: build the diff from `HEAD` plus the staged changes and pass the existing message as context, instead of describing only the fixup. → §F.4 | — |
| T35 | 💭 | Colour output (respecting `NO_COLOR` and non-TTY) and a documented error taxonomy with distinct exit codes per failure class. Today an API failure and a git failure are indistinguishable to a script. → §F.5 | — |

## Block G — Git-native integration

*The tool is only ever used if it is on the path of least resistance.* → [§G](IMPROVEMENTS.md#g--git-native-integration)

| ID | Status | Task | Depends on |
| --- | --- | --- | --- |
| T36 | 💭 | `prepare-commit-msg` hook + `clerk --install-hook` / `--uninstall-hook`. Must no-op for merge, squash, rebase and `-m`-supplied messages, and must never block a commit when the API is down. → §G.1 | T21 |
| T39 | 💭 | `.pre-commit-hooks.yaml` so the tool is installable through the `pre-commit` framework the rest of the Python world already runs. → §G.4 | T28, T36 |

## Block H — Beyond a single commit

*Same inputs, much larger product. The pipeline "read git history → structure it →
write prose about it" is not specific to one commit.* → [§H](IMPROVEMENTS.md#h--beyond-a-single-commit)

| ID | Status | Task | Depends on |
| --- | --- | --- | --- |
| T40 | 💭 | **`clerk --split`** — propose a set of logical commits from one mixed working tree (grouped by subsystem/intent), then stage and commit them in order, each with its own message. Directly attacks the reason bad commit messages exist: the commit itself was never coherent. The most ambitious task here. → §H.1 | T14, T30 |
| T41 | 💭 | `clerk changelog <range>`: generate or roll Keep a Changelog entries from the commits in a tag range. Dogfoods this repo's own release flow and closes the loop with `scripts/bump_version.py`. → §H.2 | — |
| T42 | 💭 | `clerk release-notes <range>`: human-facing notes grouped by user benefit for the GitHub Release body — a different register from the changelog, not a rename of it. → §H.2 | T41 |
| T43 | 💭 | `clerk bump --suggest`: read the commits since the last tag and recommend patch/minor/major, with the breaking-change detection the Conventional Commits spec already implies. Feeds the existing publish workflow. → §H.3 | T41 |
| T44 | 💭 | `clerk pr`: title + description for the current branch from its whole commit range, printable or pipeable to `gh pr create`. → §H.4 | T41 |

## Block I — Distribution & reach

*A tool nobody can find is a tool nobody uses.* → [§I](IMPROVEMENTS.md#i--distribution--reach)

| ID | Status | Task | Depends on |
| --- | --- | --- | --- |
| T45 | 💭 | A GitHub Action that posts a suggested commit message / PR title as a PR comment — the tool's own best advertisement, running where developers already are. → §I.1 | T44 |
| T46 | 💭 | Packaging beyond PyPI: Homebrew tap, Scoop manifest, documented `uvx commitclerk`, and a single-file release asset with a published SHA-256 (the curl path is already advertised in the README but unsigned). → §I.2 | — |
| T47 | 💭 | Grow the landing page into a real docs site once the README outgrows itself — the README stays the canonical quick start and never becomes a stub. → §I.3 | — |
| T48 | 💭 | A `recipes/` directory of ready-made rule packs: Angular convention, strict Conventional Commits, ticket-mandatory enterprise, pt-BR. Turns configuration into a shareable ecosystem. → §I.4 | T26 |
| T49 | 💭 | A demo GIF / asciinema cast at the top of the README. For a CLI this is the single highest-leverage adoption change in the whole roadmap, and it costs an afternoon. → §I.5 | — |

## Block J — Quality engineering

*The prompt is the product. There is currently no way to change it and know whether
output got better or worse.* → [§J](IMPROVEMENTS.md#j--quality-engineering)

| ID | Status | Task | Depends on |
| --- | --- | --- | --- |
| T50 | 💭 | Golden fixture corpus: real diffs (doc-only, mixed, rename-heavy, lockfile-dominated, binary) with expected classification, asserted **offline** against the deterministic parts of the pipeline. → §J.1 | T14 |
| T51 | 💭 | Prompt evaluation harness: run the corpus through a live model behind an opt-in env flag, score with a judge model, report regressions. The safety net that makes prompt changes reviewable. → §J.2 | T50 |
| T52 | 💭 | `PROMPT_VERSION` constant, surfaced by `--verbose` and recorded in eval output, so a quality result is attributable to a specific prompt. → §J.2 | — |
| T53 | 💭 | A fake-provider test double so end-to-end paths (commit, hook, split) are testable with no API key and no network. → §J.3 | — |
| T54 | 💭 | A `--help` snapshot test, so a CLI surface change is always a reviewed diff and never an accident. → §J.4 | — |
| T55 | 💭 | Split `commitclerk.py` **only** if it passes ~800 lines, and then into a package that still builds a single-file artifact — the "read the whole thing before trusting it" promise survives the refactor. → §J.5 | — |

---

## Suggested order (not binding)

If you want the highest value per unit of effort, roughly:

1. **T49** — trivial, and it fixes the discovery problem.
2. **T16, T11** — the diff pipeline's honesty gaps, in the tool's own core competence.
3. **T5** — retry on 429/5xx: resilience for almost no code.
4. **T25, T28** — config plus lint; together they unlock team adoption.
5. **T19, T21** — the two blockers for corporate approval.
6. **T7, T8** — the quality jump nobody else in this niche ships.
7. **T40, T41** — the product expansion.
