# Task counter

A terse **index**, not a memory. Counter, next block letter, one line per shipped
task. Nothing else. The implementation story goes in the commit message and the
`CHANGELOG.md` bullet — never here.

See [`.claude/skills/commitclerk-roadmap-docs`](../.claude/skills/commitclerk-roadmap-docs/SKILL.md).

- **Next free task number:** `T56`
- **Next free block letter:** `K` (A–J are in use)

T-numbers are never reused and never renumbered, even when a task is dropped.
Block letters follow the same rule. `CHANGELOG.md` — not `ROADMAP.md` — is
authoritative for what actually shipped, because the roadmap is pruned as tasks
land.

## Shipped log

Format, exactly one line per task:
`- **T<n> SHIPPED** (Block X §Y — short title) — YYYY-MM-DD.`

- **T38 SHIPPED** (Block G §G.3 — POSIX wrapper + `git add -A` staging fix) — 2026-07-27.
- **T37 SHIPPED** (Block G §G.2 — `git-clerk` entry point) — 2026-07-27.
- **T13 SHIPPED** (Block C §C.1 — per-file diff budget) — 2026-07-27.
