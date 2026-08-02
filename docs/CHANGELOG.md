# commitclerk — Shipped Ledger

> What has **shipped**, indexed by Block — one entry per task, written by `roadkeep ship`.
> `git log` is authoritative for detail. Active work lives in [ROADMAP.md](ROADMAP.md);
> design rationale for unshipped work lives in [IMPROVEMENTS.md](IMPROVEMENTS.md).
>
> An entry is its roadmap line with the marker set to ✅ and the `deps` and `→ §T<n>`
> fields dropped — the rationale section is deleted when the task ships, so a pointer to
> it would not resolve. The block headings mirror ROADMAP.md.
>
> **This is not the release changelog.** [`../CHANGELOG.md`](../CHANGELOG.md) is the
> published, user-facing, version-grouped artefact linked from PyPI, and a shipped task
> still adds its bullet there. This file answers "is T*n* done?"; that one answers "what
> changed in 0.4.0?".
>
> Tasks that shipped before the backlog moved to `roadkeep` — all of Block A and
> everything up to T64 that is no longer in the roadmap — were recorded in
> `../CHANGELOG.md` and in `git log`, and are not re-imported here.

## Block B — Context beyond the diff

- ✅ **T9** **The issue key is in the branch name and never reaches the message** — a config-gated regex over the branch name appends a `Refs: PROJ-123` trailer to the finished message, after the model rather than through it, so the key cannot be paraphrased or invented.
- ✅ **T12** **Intent lives in the author's head and the tool has nowhere to read it** — a one-off `--context "<note>"` and a standing `.clerk/context.md` both reach the prompt ahead of the diff, strictly additive and framed as the WHY rather than as work this commit performed.

## Block C — Diff intelligence

- ✅ **T17** **A commit larger than any budget is only trimmed, so its tail is never described** — summarizing each oversized file separately and writing the message from the summaries is the one path that scales past a context window.

## Block D — Trust & safety

- ✅ **T61** **One switch hides two very different data flows** — `--no-examples` refuses past commit message text on its own, so a team can keep the counts-and-shapes fingerprint while `--no-house-style` still refuses both.
- ✅ **T19** **A staged secret leaves the machine before anything has looked at it** — The staged diff is scanned for credential shapes and high-entropy tokens before the first request, refusing with exit 3 and naming the file and line but never the match.
- ✅ **T21** **A hook that calls an API hard-blocks the commit when the network is down** — `--offline` writes the whole message locally with no key, no network and no provider resolved, taking the type from the file classes and never guessing feat: or fix:.
- ✅ **T20** **A repository with three sensitive files cannot allow the tool at all** — `.clerkignore` withholds a matched file's body from every request, leaving its path and line counts, and runs before the secret scan so exclusion is also the way out of a false positive.
- ✅ **T23** **History cannot say which commits were AI-assisted** — An opt-in `assisted_by` writes `Assisted-by: commitclerk <version> (<model>)` after the model has answered, and says `(offline, no model)` on the path that called none.

## Block E — Configuration & conventions

- ✅ **T25** **A team convention is retyped as flags on every commit** — a `.clerk.json` at the repository root and a `~/.config/clerk/config.json` are read through one precedence ladder, CLI > env > project > user > default, written in a single function.

## Block F — Interaction & UX

## Block G — Git-native integration

## Block H — Beyond a single commit

## Block I — Distribution & reach

## Block J — Quality engineering
