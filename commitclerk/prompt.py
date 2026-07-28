"""The prompt: the rules the model must follow, and how the request is framed.

This is the product. Changing anything here changes every message the tool
writes, which is why the rules are one long string per instruction rather than
prose to be rewrapped.
"""

from __future__ import annotations

from .files import class_mix

_RULES = """- Describe what THIS commit changes, not what the changed text says. Prose added to documentation (CHANGELOG, ROADMAP, README, *.md) often describes features in past/present tense that ALREADY shipped in earlier commits; never restate that as work implemented in this commit.
- Title: imperative mood, max 72 chars, no trailing period.
- Use a Conventional Commits prefix when applicable (feat:, fix:, chore:, refactor:, docs:, test:, build:, perf:). Documentation-only changes use docs:.
- Body: 2 to 6 bullets summarizing the WHY and key changes; describe intent and behaviour, not a file-by-file diff replay.
- Bullets start with '- ' on their own line.
- Read the change summary for facts the diff body cannot show. A rename is a move, never a rewrite; a mode change is a permission change; a binary file has a size change and no readable content, so never invent what is inside one.
- Each changed file is annotated with its class: code, test, docs, generated, config, vendor, binary. Pick the type prefix from the classes that are the point of the commit — only docs means docs:, only test means test:, only config or generated means chore: or build:. Never make a generated, vendored or binary file the subject of the message and never narrate its contents; when such files accompany a real change, mention them in at most one bullet as a consequence ("regenerated the lockfile").
- No markdown headers, no code fences, no emojis."""


def _system_prompt(*, body_only: bool) -> str:
    if body_only:
        return (
            "You are a git commit message body generator. Given a unified diff and the commit "
            "title the author already chose, produce ONLY the body: 2 to 6 bullets, each starting "
            "with '- ' on its own line, summarizing the WHY and key changes. No title line, no "
            "leading blank line, no markdown headers, no code fences, no emojis.\n\nRules:\n" + _RULES
        )
    return (
        "You are a git commit message generator.\n"
        "Given a unified diff, produce a commit message with this exact shape:\n\n"
        "<title>\n<blank line>\n- <bullet>\n- <bullet>\n- <bullet>\n\nRules:\n"
        + _RULES
        + "\nReturn only the commit message text."
    )

def build_user_prompt(
    diff: str,
    files: list[str],
    *,
    title: str | None = None,
    guard: str = "",
    summary: str = "",
    classes: dict | None = None,
) -> str:
    classes = classes or {}
    parts = ["Files changed:"] + [
        f"- {f} ({classes[f]})" if f in classes else f"- {f}" for f in files
    ]
    if classes:
        parts += [f"Class mix: {class_mix(classes)}"]
    if summary:
        # Before the diff, and outside its budget: when a large diff is trimmed
        # this is the part that still describes the whole change.
        parts += ["", "Change summary (git --stat --summary):", summary]
    if title is not None:
        parts += ["", f"Commit title (already chosen by the author, do not repeat it): {title}"]
    parts += ["", "Unified diff:", diff]
    if guard:
        # Last, on purpose. Measured against gpt-4o-mini: with the guard placed
        # before the diff, 48 lines of changelog prose came after it and won — the
        # model still wrote "feat: implement real-time collaboration" for a commit
        # whose only code change was a docstring. Read after the diff, it obeys.
        parts += ["", guard]
    return "\n".join(parts)

