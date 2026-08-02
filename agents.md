# commitclerk — Development Guide

**What this is.** A CLI that writes the git commit message from your staged diff. Zero
runtime dependencies, Python ≥3.8, shipped both as a package and as one auditable file.
Its one genuinely differentiated idea: **it refuses to describe documentation prose as
work that was implemented** — a `CHANGELOG.md` edit never becomes a fake `feat:`.

**The rule every design question comes back to.** *The tool never writes history that did
not happen.* A message that describes an earlier commit, an instruction's own example, or
a file the diff does not contain is the product failing at the thing it exists to do —
which is why §T60 is the top of the queue and why the evaluation harness (§T51) scores
"did the output contain a phrase that appears only in the rules" as a regression.

## Layout

```
commitclerk/          the package — cli, gitio, diffing, files, history, prompt, providers
dist/commitclerk.py   the standalone build; scripts/build_single_file.py --check gates it
tests/                unittest (not pytest); COMMITCLERK_SOURCE=dist runs them against the build
docs/ROADMAP.md       active backlog, one line per task (T<n>)
docs/CHANGELOG.md     the task ledger, indexed by block — written by `roadkeep ship`
docs/IMPROVEMENTS.md  design rationale, one §T<n> section per UNSHIPPED task
docs/STRATEGY.md      positioning, distribution, licensing — never a backlog
CHANGELOG.md          the published release notes (Keep a Changelog), grouped by version
README.md, README.pt-BR.md, docs/llms.txt, docs/index.html   the user-facing surfaces
roadkeep.toml         this project's prefix, paths, limits, markers and budgets
```

## The backlog is owned by `roadkeep`, not by hand

The four `docs/` files above are governed: **an `Edit` on one is denied and names the
command instead.** Ids, the `→ §T<n>` pointer, the `(deps: …)` annotations and every
length limit are derived or refused at insertion, so a line is correct before it is
written. The write path — which command, what it derives, how work is picked — is the
**roadkeep skill**, loaded on the turns that touch a governed file and costing nothing on
the turns that do not. Nothing here repeats it; a rule in two files is a rule two files
can disagree about.

Start a task with `roadkeep brief` (or the `mcp__roadkeep__brief` tool): it picks, and it
prints the line, its rationale, the deps and the binding non-goals in one call.
`docs/last-task.md` is gone — `roadkeep next-id` derives the answer from the files.

`roadkeep lint` **must pass on `docs/`**, and it exits 1 on any violation, dangling
pointer, orphan section, unsatisfiable dep or over-budget always-loaded file. CI runs it.

## Non-goals are binding

[docs/ROADMAP.md](docs/ROADMAP.md) → "Non-goals", which `brief` prints with every task.
The hardest of them: **zero runtime dependencies in the core path.** A task that needs a
package is a task that needs a redesign, or a `STRATEGY.md` decision first. Positioning,
naming, distribution and licensing are `STRATEGY.md` prose and never a numbered task.

## Build and test

- `python -m unittest discover -s tests` from the repo root. No install step, no pytest.
- `python scripts/build_single_file.py` after touching `commitclerk/`, and `--check` is
  what CI runs — a stale `dist/commitclerk.py` fails the build.
- `python -m unittest discover -s tests` with `COMMITCLERK_SOURCE=dist` runs the same
  suite against the built artifact. Both paths ship, so both are tested.
- `ruff check` with the config in `pyproject.toml`. The floor is **3.8**: no `tomllib`,
  no `match`, no `X | Y` annotations at runtime.
- **Every string that can reach a terminal must be ASCII** (§T57). Prose files may use
  typography freely; `--help`, errors and notices may not.

## Committing

**One task → one commit, the instant it is validated.** What `ship` wrote goes in the
*same* commit as the code, so the docs never describe a state that did not ship, and a
batch of ≥2 tasks is **not** permission to batch: `/loop`, one task per iteration. Use
`run-commit.cmd -m "<conventional-commits title>"` from the repo root, **`-m` always** and
ASCII — this repo's product is the commit tool, so every task is also the dogfood run.
`run-commit.cmd` stages everything, so a tree holding unrelated work wants the task's
paths staged and `python -m commitclerk -m …` instead.

## Shipping a user-facing change is a gate, not an afterthought

A flag that lands in the code and never reaches `README.md`, `README.pt-BR.md` and
`docs/llms.txt` is a bug — six surfaces are updated by hand per flag today, which is what
§T58 exists to test. The decision procedure (is it user-facing, which surfaces, the
translation, `SECURITY.md` when the data flow changes) is
[`.claude/skills/commitclerk-user-docs`](.claude/skills/commitclerk-user-docs/SKILL.md),
loaded on the turns that ship one.

## This file is scaffolding

What stays here is only what a turn touching no governed file needs: the product's one
rule, where the code is, how to build it and how to commit it. Its budget is `[budgets]`
in `roadkeep.toml`, held by `lint` and not by this sentence.
