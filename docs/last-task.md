# Task counter

A terse **index**, not a memory. Counter, next block letter, one line per shipped
task. Nothing else. The implementation story goes in the commit message and the
`CHANGELOG.md` bullet — never here.

See [`.claude/skills/commitclerk-roadmap-docs`](../.claude/skills/commitclerk-roadmap-docs/SKILL.md).

- **Next free task number:** `T57`
- **Next free block letter:** `K` (A–J are in use)

T-numbers are never reused and never renumbered, even when a task is dropped.
Block letters follow the same rule. `CHANGELOG.md` — not `ROADMAP.md` — is
authoritative for what actually shipped, because the roadmap is pruned as tasks
land.

## Shipped log

Format, exactly one line per task:
`- **T<n> SHIPPED** (Block X §Y — short title) — YYYY-MM-DD.`

- **T6 SHIPPED** (Block A §A.4 — repair a rejected request parameter) — 2026-07-27.
- **T5 SHIPPED** (Block A §A.4 — retry with backoff/jitter + `--timeout`) — 2026-07-27.
- **T4 SHIPPED** (Block A §A.3 — keyless `--provider ollama` preset) — 2026-07-27.
- **T3 SHIPPED** (Block A §A.2 — Anthropic Messages adapter) — 2026-07-27.
- **T2 SHIPPED** (Block A §A.1 — `--base-url` / `$OPENAI_BASE_URL`) — 2026-07-27.
- **T1 SHIPPED** (Block A §A.1 — provider adapter table + `--provider`) — 2026-07-27.
- **T56 SHIPPED** (Block I §I.3 — GitHub Pages landing page + logo) — 2026-07-27.
- **T38 SHIPPED** (Block G §G.3 — POSIX wrapper + `git add -A` staging fix) — 2026-07-27.
- **T37 SHIPPED** (Block G §G.2 — `git-clerk` entry point) — 2026-07-27.
- **T13 SHIPPED** (Block C §C.1 — per-file diff budget) — 2026-07-27.
