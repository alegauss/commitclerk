---
name: commitclerk-user-docs
description: How to propagate a shipped, user-facing change into commitclerk's documentation surfaces — README.md, README.pt-BR.md, docs/llms.txt, docs/index.html, the argparse help and module docstring, SECURITY.md and the release CHANGELOG.md. Use whenever a task ships a flag, a provider, an exit code, an environment variable or anything that changes what leaves the machine. Does not cover the roadmap files: those are written by roadkeep.
---

# Propagating a shipped change to the user-facing docs

The backlog files (`docs/ROADMAP.md`, `docs/CHANGELOG.md`, `docs/IMPROVEMENTS.md`,
`docs/STRATEGY.md`) are **not** this skill's business — `roadkeep ship` writes them and an
`Edit` on them is denied. This skill starts where `ship` ends: the same commit still has to
carry the documentation a *user* reads.

## 1. Is it user-facing?

Would someone **using** commitclerk — running the CLI, writing a config file, installing a
hook, reading exit codes in a script — do something differently because this shipped?

**No** (internal refactor, test harness, CI, packaging plumbing): it stops at the release
`CHANGELOG.md` bullet. Do not invent README prose for internal work.

**Yes**: continue. A new flag is rarely one edit.

## 2. The release changelog, always

Root [`CHANGELOG.md`](../../../CHANGELOG.md) — *not* `docs/CHANGELOG.md`, which is the task
ledger. Add the bullet under `## [Unreleased]` in the right Keep a Changelog section
(`Added` / `Changed` / `Fixed` / `Removed` / `Deprecated` / `Security`). It gets no heading
of its own and the `T<n>` number never appears there: T-numbers are internal. Write what
changed and why it matters to a user, not which function was refactored.

## 3. Every surface the change touches

In `README.md`:

- the **Usage** synopsis line (`clerk [-m TITLE] [--dry-run] …`)
- the **flag table**
- the **Examples** block, if the flag is non-obvious
- the **Exit codes** table, if it adds one
- the **Highlights** table, if it is a headline capability
- the **Configuration** / **Privacy and cost** sections, if it changes what is sent over
  the network or read from the environment
- the **Roadmap** section, if the shipped task was listed there

And outside it:

- `commitclerk/cli.py`'s **`argparse` help** and the **module docstring** — documentation
  too, and the only docs an offline user has. Both must be **ASCII** (§T57).
- [`docs/llms.txt`](../../../docs/llms.txt), which is the machine-readable surface and
  goes stale silently.
- [`docs/index.html`](../../../docs/index.html) — the landing page is a *pitch*, so it
  only changes for a headline capability, never for every flag.

## 4. Mirror into `README.pt-BR.md` in the same commit

A translation that lags is worse than none, because it silently documents behaviour that
no longer exists. Same structure, same tables, same order — translate the prose, never the
flag names, the exit codes or the code samples.

## 5. `SECURITY.md` when the data flow changes

New provider, new endpoint, new file read, new redaction path, anything newly included in
the request: update the data-flow statement. This is the project's core trust claim, and a
stale `SECURITY.md` is a bug of the same severity as a broken flag.

## 6. Rebuild the artifact

`python scripts/build_single_file.py` after any change under `commitclerk/`, and remember
that `README.md` quotes `dist/commitclerk.py`'s line count as evidence it is still small
enough to audit — a number that has gone stale three times in one afternoon (§T58).

## Write for the user, not for the commit

The READMEs explain *what it does and how to use it*. They are not a changelog and not a
design-rationale dump — never paste `docs/IMPROVEMENTS.md` prose verbatim.

All of this happens **in the shipping task's own commit**. Under `/loop`, that means per
task, per iteration: everything lives in one repository, so there is nothing to defer.
