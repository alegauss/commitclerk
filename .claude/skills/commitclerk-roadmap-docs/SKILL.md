---
name: commitclerk-roadmap-docs
description: How to maintain the commitclerk roadmap/docs — the four files (docs/ROADMAP.md, CHANGELOG.md, docs/IMPROVEMENTS.md, docs/STRATEGY.md), their single-responsibility split, and the cross-file update rules. Also how to propagate a shipped, user-facing change into the two READMEs (README.md + README.pt-BR.md) and the CLI reference tables. Use whenever adding a new task, marking a task shipped, editing any of those files, or picking the next T-number (docs/last-task.md). Covers task numbering, non-goals, keeping the files in sync, and the user-docs decision.
---

# Roadmap & docs maintenance (commitclerk)

## ⛔ READ FIRST — one task, one commit (non-negotiable)

**You may NOT do more than one task before committing.** This is the single most
violated rule, so it is stated up front and it is absolute:

- **One task → one `run-commit.cmd`.** The moment a task is complete and validated,
  do the doc sync + `cd` to the repo root + `run-commit.cmd -m "<ascii title>"`
  **before touching the next task.** Finishing a task means *the commit landed* —
  code + `ROADMAP`/`CHANGELOG`/`last-task.md` sync in that one commit.
- **A multi-task request (e.g. "execute Block D", or a list of `T<n>`s) is NOT
  permission to batch.** It is a request to run tasks **one-at-a-time, committing
  after each.** Never implement task 2 while task 1 is uncommitted. A single giant
  diff spanning many tasks with one commit (or no commit) at the end is the failure
  this rule exists to prevent.
- **For any batch of ≥2 tasks you MUST drive it with the `/loop` skill**
  (self-paced): exactly one task per iteration, `run-commit.cmd` at the end of the
  iteration, then let the loop advance. Do not hand-roll a loop that defers commits.
- **Self-check before starting task N+1:** run `git status` / `git log -1`. If the
  previous task's work is not already committed, STOP and commit it first.

There is a second reason this rule is load-bearing *here specifically*: this repo's
product **is** the commit tool. Every task is a chance to dogfood `run-commit.cmd`,
and a batched mega-commit destroys that signal.

The full commit + batch mechanics are rules 7–8 below.

---

The roadmap is **split across four files** that must be kept in sync. Each has one
job — never duplicate content between them, and when you touch one, check whether a
sibling needs updating:

| File | Single responsibility | Granularity |
| --- | --- | --- |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | **Task status** — the *only* source of truth for what's done/active. Active backlog only (📋 designed · 💭 idea · ⏳ partial · 🛠 in-progress). | one row per task |
| [`CHANGELOG.md`](CHANGELOG.md) | What has **shipped**, in [Keep a Changelog](https://keepachangelog.com/) form, grouped by release. `git log` is authoritative for detail. | one bullet per shipped task |
| [`docs/IMPROVEMENTS.md`](docs/IMPROVEMENTS.md) | **Design rationale** (the what/why/how) for *unshipped* sections only. No status tables, no shipped implementation reports. | prose per active section |
| [`docs/STRATEGY.md`](docs/STRATEGY.md) | Positioning, audience, distribution, licensing, deprecation bets. Not a backlog. | prose |

**`CHANGELOG.md` lives at the repo root, not in `docs/`,** and is release-shaped
rather than task-shaped — it is a published artifact linked from PyPI. A shipping
task adds its bullet under `## [Unreleased]` in the right Keep a Changelog section
(`Added` / `Changed` / `Fixed` / `Removed` / `Deprecated` / `Security`). It does
**not** get its own heading, and the `T<n>` number does **not** appear there —
T-numbers are internal. Keep the bullet user-facing: what changed and why it
matters, not which function was refactored.

**Task numbering — the next free `T<n>` lives in
[`docs/last-task.md`](docs/last-task.md).** Read it before adding a task, use
`T<n+1>`, then bump the counter + append a log line. T-numbers are **never
reused and never renumbered**, even when a task is dropped — a dropped task is
struck through in the roadmap or removed, and its number simply retires. Never
infer the next number from a block's header range or a `git log` scan.

**`docs/last-task.md` is a terse INDEX, not a memory.** It holds the counter, the
next **block letter**, and a **one-line-per-shipped-task log** — nothing more.

- **A log entry is exactly ONE line**, of the form
  `- **T<n> SHIPPED** (Block X §Y — short title) — YYYY-MM-DD.`
  The implementation story — files, gotchas, decisions — goes in the **commit
  message** and the **`CHANGELOG.md` bullet**, *never* here.
- **Do not turn a log entry into an implementation report.** Multi-sentence
  paragraphs with gotchas are the anti-pattern this file exists to avoid. A
  genuinely reusable gotcha belongs in auto-memory or `CLAUDE.md`, not here.

**The cross-file update rules — follow these every time:**

1. **When a task ships:** delete its row from `docs/ROADMAP.md`, add its bullet to
   `CHANGELOG.md` under `## [Unreleased]`, and **delete** its design subsection
   from `docs/IMPROVEMENTS.md`. `git log` is the history — do **not** leave a
   shipped implementation report in `IMPROVEMENTS.md` or re-accrete one. This is
   the founding rule. **Then run the user-docs decision** (below) — a shipped
   user-facing flag that never reaches the READMEs is a bug.
2. **When you add a new task:** add the row to `docs/ROADMAP.md` (with a
   `→ §x.y` pointer and its deps) and, if it needs design, add the rationale
   subsection to `docs/IMPROVEMENTS.md`. Status lives **only** in `ROADMAP.md` —
   don't put ✅/📋 markers inside `IMPROVEMENTS.md` prose.
3. **Status belongs to exactly one file.** If a status marker in `IMPROVEMENTS.md`
   disagrees with `ROADMAP.md`/`CHANGELOG.md`, the roadmap files win — fix or
   remove the stale marker.
4. **Keep entries terse.** A task row is *what + why + pointer* (~1 sentence).
   Implementation detail goes in code/commits, not the table cell. Never put
   multi-paragraph release notes inside a markdown table cell.
5. **Strategy ≠ backlog.** Positioning, naming, distribution and licensing
   discussion goes in `STRATEGY.md`, never as a numbered task.
6. **Non-goals are binding.** `docs/ROADMAP.md` → "Non-goals" lists things
   deliberately *not* to build — check it before proposing new work, and treat
   "zero runtime dependencies in the core path" as the hardest of them. A task
   that needs a dependency is a task that needs a redesign or a `STRATEGY.md`
   decision first.
7. **Commit the instant a task finishes — before starting the next (see the ⛔
   block at the top).** A task is not "done" until
   `run-commit.cmd -m "<conventional-commits title>"` has landed. Do the doc sync
   (rules 1–2, bump `docs/last-task.md`) **in the same commit** as the code, so the
   docs never drift from what shipped. `cd` to the repo root first, and keep the
   `-m` title ASCII.
8. **A batch of ≥2 tasks MUST run under `/loop` — mandatory, not a suggestion.**
   Exactly one task per iteration, `run-commit.cmd` at the end of that iteration
   (rule 7), then advance. Only a genuinely single-task ask skips `/loop`.

## Propagating to user-facing documentation

There is no separate docs site (yet — that's a roadmap task). The **user-facing
documentation surface is the README pair**, and it is a *gate*, not an
afterthought:

```
README.md          <- canonical, English
README.pt-BR.md    <- translation, must not drift
```

**Every time a task ships, after the internal doc sync (rule 1), run this decision:**

1. **Is it user-facing?** Would someone *using* commitclerk (running the CLI,
   writing a config file, installing a hook, reading exit codes in a script) do
   something differently because this shipped? If **no** — internal refactor, test
   harness, CI, packaging plumbing — it stops at `CHANGELOG.md`. Don't invent
   README prose for internal work.
2. **If yes, update every surface it touches.** A new flag is rarely one edit.
   Check all of these in `README.md`:
   - the **Usage** synopsis line (`clerk [-m TITLE] [--dry-run] …`)
   - the **flag table**
   - the **Examples** block, if the flag is non-obvious
   - the **Exit codes** table, if it adds one
   - the **Highlights** table, if it's a headline capability
   - the **Configuration**/**Privacy and cost** sections, if it changes what is
     sent over the network or read from the environment
   - the **Roadmap** section — remove the line if it was listed there
   - `commitclerk.py`'s **module docstring** and `argparse` help, which are
     documentation too and are the only docs an offline user has
3. **Mirror into `README.pt-BR.md` in the same commit.** A translation that lags
   is worse than no translation, because it silently documents behaviour that no
   longer exists. Same structure, same tables, same order — translate the prose,
   never the flag names, exit codes, or code samples.
4. **Anything that changes what leaves the machine also touches `SECURITY.md`.**
   New provider, new endpoint, new file read, new redaction path → update the
   data-flow statement there. This is the project's core trust claim; treat a
   stale `SECURITY.md` as a bug of the same severity as a broken flag.
5. **Write for the user, not the commit.** The READMEs explain *what it does and
   how to use it*. They are not a changelog and not a design-rationale dump. Never
   paste `IMPROVEMENTS.md` prose verbatim.

**Batch note.** When shipping a run of tasks under `/loop` (rule 8), the user-docs
decision runs **per task and in that task's own commit** — unlike a multi-repo
setup, everything here lives in one repo, so there is no reason to defer it.
