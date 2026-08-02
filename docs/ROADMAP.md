# commitclerk — Roadmap (active backlog)

> **Single source of truth for task status.** Flat, one line per task.
> Only **unshipped** work lives here (💭 idea · 📋 designed · ⏳ partial · 🛠 in-progress).
> Shipped work moves to [CHANGELOG.md](CHANGELOG.md); the user-facing release notes are
> [`../CHANGELOG.md`](../CHANGELOG.md), which is a published artifact and not a task
> ledger. Design rationale lives in [IMPROVEMENTS.md](IMPROVEMENTS.md); positioning and
> distribution bets live in [STRATEGY.md](STRATEGY.md).
>
> **What this is.** A CLI that writes the commit message from the staged diff, with one
> genuinely differentiated idea: **it refuses to describe documentation prose as work
> that was implemented.** Every line below answers one of three questions — will it scale
> technically (Blocks B, C), can a team actually adopt it (D, E, F, G), and is a commit
> message the whole product (H, I, J).
>
> **An entry here is one sentence: what + why + `→` pointer.** The symptom is what does
> not work, never the name of the fix — a line named after its solution cannot be
> falsified, so it never gets closed, only abandoned.
>
> **This file is written by `roadkeep`, never by hand:** `add`, `status`, `amend`, `ship`,
> `retire`. Ids are derived, never chosen; `docs/last-task.md` is gone because `next-id`
> answers it from the files.
>
> **How to pick work:** `roadkeep brief` — in-progress first, then `priority` in
> `roadkeep.toml`, then the lowest-numbered task whose deps are all shipped.

## Block B — Context beyond the diff

*The founding insight is that the diff alone misleads. History now answers "how does this
repo write commits" and the tree answers "which package is this". What is left is intent,
which lives in the branch name and in the author's head.*

- 💭 **T9** (deps: T25) **The issue key is in the branch name and never reaches the message** — a configurable regex over `feat/PROJ-123-thing` emits a `Refs: PROJ-123` trailer, so the link between a commit and its ticket stops being retyped. → §T9
- 💭 **T12** (deps: T25) **Intent lives in the author's head and the tool has nowhere to read it** — a one-off `--context "<note>"` and a standing `.clerk/context.md` are the two shapes intent arrives in, and neither is derivable from a diff. → §T12

## Block C — Diff intelligence

*Every file reaches the model, classified, with generated noise collapsed, the doc guard
honest on mixed commits, and partial staging called out. What is left is the commit no
budget can fit.*

- 💭 **T17** (deps: —) **A commit larger than any budget is only trimmed, so its tail is never described** — summarizing each oversized file separately and writing the message from the summaries is the one path that scales past a context window. → §T17

## Block D — Trust & safety

*This block is what turns "a neat script" into "a tool a company can approve".*

- 💭 **T19** (deps: —) **A staged secret leaves the machine before anything has looked at it** — scanning for known key shapes and high-entropy strings before the request is sent, refusing by default, is the worst outcome this tool can have and the cheapest to prevent. → §T19
- 💭 **T20** (deps: —) **A repository with three sensitive files cannot allow the tool at all** — paths whose contents are never transmitted, replaced by a filename-and-linecount placeholder, make the allow decision per file instead of per repository. → §T20
- 💭 **T21** (deps: —) **A hook that calls an API hard-blocks the commit when the network is down** — a deterministic LLM-free message, type from file classes and bullets grouped by directory, has no key, no network and no failure mode. → §T21
- 💭 **T22** (deps: T53) **The no-egress claim is documented and never tested** — running the suite with socket creation monkeypatched to raise turns the claim into a build failure the moment it stops being true. → §T22
- 💭 **T23** (deps: T25) **History cannot say which commits were AI-assisted** — an opt-in `Assisted-by: commitclerk <version> (<model>)` trailer is what a team needing provenance adds by hand today, and it stays off by default. → §T23
- 💭 **T24** (deps: T19) **`SECURITY.md` does not say what leaves the machine** — the data flow now has two injection vectors, diff content and past commit messages replayed verbatim as worked examples, and a reader can audit neither. → §T24
- 📋 **T61** (deps: —) **One switch hides two very different data flows** — `--no-house-style` disables the fingerprint (counts and shapes) and the worked examples (past message text, verbatim) together, and a team can want the first without the second. → §T61

## Block E — Configuration & conventions

*Every team's commit convention is slightly different, and the only way to encode one
today is to fork `_RULES` — which is how a tool acquires a thousand incompatible forks
and no ecosystem.*

- 💭 **T25** (deps: —) **A team convention is retyped as flags on every commit** — a project config file with documented precedence, CLI > env > project > user > default, is what every other task in this block waits on. → §T25
- 💭 **T26** (deps: T25) **Encoding a team's convention means forking `_RULES`** — replacing or appending to the rules from a file named by flag or environment variable is how the tool gets an ecosystem instead of a thousand private patches. → §T26
- 💭 **T27** (deps: T25) **The message is English whatever language the team works in** — a language flag matches the register the repository is already written in, and this one ships a pt-BR README against an English-only generator. → §T27
- 💭 **T28** (deps: T25) **An existing message cannot be checked without generating a new one** — validating a file or `HEAD` against the same rules with zero API calls makes the tool usable as a `commit-msg` hook and in CI by people who never generate. → §T28
- 💭 **T29** (deps: T28) **The model's type and scope are trusted without being checked** — one repair retry and then a loud failure is the only outcome that keeps an off-convention message out of history. → §T29

## Block F — Interaction & UX

*The current flow is fire-and-commit: if the message is wrong, the only recourse is
`git commit --amend`.*

- 💭 **T30** (deps: —) **A wrong message is only fixable after it is already committed** — accept, edit, regenerate or quit before the commit is the loop the tool is missing, with a flag keeping today's non-interactive behaviour for scripts. → §T30
- 💭 **T31** (deps: T30) **Editing the message means rewriting it after the commit** — opening it in `$EDITOR` or `core.editor` first is the whole distance between a good draft and a correct message. → §T31
- 💭 **T32** (deps: —) **A slow or local model shows a frozen terminal for thirty seconds** — streaming the completion is the difference between waiting and wondering whether the process hung. → §T32
- 💭 **T33** (deps: T52) **What a run costs is invisible** — model, prompt and completion tokens, estimated cost, elapsed time and prompt version answer it in one flag, with a quiet counterpart for hook use. → §T33
- 💭 **T34** (deps: —) **An amended commit is described by its fixup alone** — building the diff from `HEAD` plus the staged changes and passing the existing message as context is what makes the rewritten message true. → §T34
- 💭 **T35** (deps: —) **An API failure and a git failure are indistinguishable to a script** — a documented error taxonomy with a distinct exit code per failure class is what a caller branches on, and colour has to respect `NO_COLOR` and a non-TTY. → §T35
- 💭 **T59** (deps: —) **Nothing budgets the reply, so a verbose model fails with "returned no message text"** — Anthropic's cap is hard-coded at 8 192 and OpenAI's is unset, so the budget has to be provider-agnostic to be a budget at all. → §T59
- 📋 **T62** (deps: —) **There is no way to see what was actually sent** — nine sources now feed one request, from rules and house style to the guard and the diff, and a prompt nobody can print is a prompt nobody can review. → §T62
- 💭 **T63** (deps: T33) **Nothing bounds the size of the whole request** — the diff budget governs the diff alone while rules, house style, examples and guard sit beside it, so a small-context local model is overrun by context the user never asked for. → §T63

## Block G — Git-native integration

*The tool is only ever used if it is on the path of least resistance.*

- 💭 **T36** (deps: T21) **The tool runs only when the author remembers to run it** — a `prepare-commit-msg` hook and its installer put it on the path of least resistance, and it must no-op for merge, squash, rebase and a supplied message. → §T36
- 💭 **T39** (deps: T28, T36) **The framework the Python world already runs cannot install this tool** — a `.pre-commit-hooks.yaml` is the entire distance between the two. → §T39

## Block H — Beyond a single commit

*Same inputs, much larger product: "read git history, structure it, write prose about it"
is not specific to one commit.*

- 💭 **T40** (deps: T30) **A mixed working tree becomes one commit nothing can describe** — proposing a set of logical commits grouped by subsystem and staging them in order attacks the reason bad messages exist, which is that the commit was never coherent. → §T40
- 💭 **T41** (deps: —) **Changelog entries are written by hand from commits that already say it** — generating them for a tag range dogfoods this repository's own release flow and closes the loop with `scripts/bump_version.py`. → §T41
- 💭 **T42** (deps: T41) **A release body needs a different register and there is only the changelog** — notes grouped by user benefit are a separate artifact from a changelog, not a rename of one. → §T42
- 💭 **T43** (deps: T41) **The version bump is a judgement made without reading the commits** — the commits since the last tag already imply patch, minor or major, breaking changes included, and the publish workflow is waiting on the answer. → §T43
- 💭 **T44** (deps: T41) **A PR title and description are retyped from commits that already exist** — the branch's whole commit range is the input, printable or pipeable straight into `gh pr create`. → §T44

## Block I — Distribution & reach

*A tool nobody can find is a tool nobody uses.*

- 💭 **T45** (deps: T44) **Nobody meets the tool where they already work** — an Action that posts a suggested commit message or PR title as a review comment is advertising that does work. → §T45
- 💭 **T46** (deps: —) **The curl install advertised in the README is unsigned** — a Homebrew tap, a Scoop manifest, a documented `uvx` path and a release asset with a published checksum are where people actually install things. → §T46
- 💭 **T47** (deps: —) **The README is the only documentation and it is outgrowing itself** — a docs site can take the depth, as long as the README stays the canonical quick start and never becomes a stub. → §T47
- 💭 **T48** (deps: T26) **Every team writes its rule pack from nothing** — ready-made packs for the Angular convention, strict Conventional Commits, ticket-mandatory enterprise and pt-BR turn configuration into something shareable. → §T48
- 💭 **T49** (deps: —) **A CLI nobody can watch is a CLI nobody tries** — a demo cast at the top of the README is the highest-leverage adoption change on this list and it costs an afternoon. → §T49

## Block J — Quality engineering

*The prompt is the product, and there is currently no way to change it and know whether
the output got better or worse.*

- 💭 **T50** (deps: —) **The deterministic half of the pipeline is asserted against nothing** — real diffs that are doc-only, mixed, rename-heavy, lockfile-dominated and binary, with their expected classification, are the fixture every other quality task needs. → §T50
- 💭 **T51** (deps: T50) **A prompt change cannot be shown to be an improvement** — running the corpus through a live model behind an opt-in flag and scoring it with a judge is the safety net that makes a prompt edit reviewable. → §T51
- 💭 **T52** (deps: —) **A quality result cannot be attributed to a prompt** — a version constant, surfaced by the verbose flag and recorded in eval output, is what makes a score mean anything a month later. → §T52
- 💭 **T53** (deps: —) **Every end-to-end path needs an API key to test** — a fake-provider double makes commit, hook and split testable with no key and no network. → §T53
- 💭 **T54** (deps: —) **A CLI surface change reaches users without anyone reviewing it** — a `--help` snapshot test turns every change to it into a diff somebody read. → §T54
- 💭 **T57** (deps: —) **Non-ASCII output renders as `?` on a cp1252 console** — two em dashes and a retry notice shipped that way before being caught by hand, which is a portability constraint and not a style preference. → §T57
- 💭 **T58** (deps: T54) **Six documentation surfaces are updated by hand per shipped flag** — every flag and provider has to reach both READMEs and `docs/llms.txt`, and the artifact line count quoted in `README.md` went stale three times in one afternoon. → §T58
- 📋 **T60** (deps: —) **Instruction examples leak into the output** — `_RULES` illustrates a rule with `("regenerated the lockfile")` and three generations out of three emitted that phrase verbatim on commits containing no lockfile. → §T60
- 💭 **T64** (deps: —) **Line endings differ between contributors and the build compares artifact text** — pinning text files to LF removes both the `git add` warning on Windows and a check failure nobody can reproduce locally. → §T64

## Non-goals

Deliberately **not** built — check this list before proposing work:

- **No runtime dependencies in the core path.** The standard library alone is the trust story, so a task that needs a package is a task that needs a redesign or a `STRATEGY.md` decision first.
- **No telemetry, analytics, remote config or phone-home.** Not opt-in and not behind a flag, because a tool that reads a private diff earns trust by having nothing to report.
- **No hosted service and no server component.** The tool runs on your machine, which is what keeps the data-flow answer short enough to audit.
- **Never stage silently from the Python entrypoint.** Wrappers may stage and the tool reads what you chose to stage, and losing that makes it unsafe to put behind a hook.
- **No auto-push, no auto-PR, no auto-merge.** The commit is the last step, and everything after it is a decision the author has not made yet.
- **Not a code reviewer or a linter for code.** It describes changes and does not judge them, which is the only reason it can be trusted on every commit.
- **No gitmoji and no AI watermark by default.** Both stay opt-in, the provenance trailer included, because how a team signs its history is the team's choice.
- **Do not rewrite history.** No amend-by-default and no interactive rebase driving, because a tool that rewrites history can destroy work the author cannot recover.
- **Not a fork-per-team product.** Conventions are configuration, which is what Block E exists to build, and never patches to `_RULES`.
