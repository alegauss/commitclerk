"""The issue key the branch name carries, and where it goes in the message.

Nothing here is sent to the model. A trailer is a fact about the commit, not a
judgement about the diff, so it is appended to the message afterwards where it
cannot be paraphrased, dropped, or invented.
"""

from __future__ import annotations

import re

# Jira and Linear (`PROJ-123`), and GitHub (`#123`). Deliberately narrow: two to
# ten capitals before the dash, so an ISO date or a `v2-3` suffix in a branch
# name is not read as a ticket.
DEFAULT_TICKET_PATTERN = r"[A-Z]{2,10}-\d+|#\d+"

TICKET_TRAILER = "Refs"

# A git trailer line: `Key: value`, where the key is a word, possibly hyphenated.
# `feat(api):` does not match, which is what keeps a title-only message from
# being mistaken for a trailer block. Not `_TRAILER_RE`: the single-file build
# concatenates every module into one namespace, so a name history.py already
# uses would silently replace it.
_TRAILER_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*:\s")


def compile_ticket_pattern(pattern: str):
    """The pattern as a compiled regex, or None when it does not compile.

    The caller decides what an unusable pattern means; here it is only reported,
    because this module has no opinion about exit codes.
    """
    try:
        return re.compile(pattern)
    except re.error:
        return None


def ticket_key(branch: str | None, pattern: str = DEFAULT_TICKET_PATTERN) -> str | None:
    """The first issue key in `branch`, or None when there is none to find.

    `feat/PROJ-123-retry-webhooks` yields `PROJ-123`. A detached HEAD arrives
    here as the literal `HEAD`, which matches nothing, so it needs no case.
    """
    if not branch:
        return None
    compiled = compile_ticket_pattern(pattern)
    if compiled is None:
        return None
    found = compiled.search(branch)
    return found.group(0) if found else None


def add_trailer(message: str, key: str, value: str) -> str:
    """`message` with `key: value` in its trailer block.

    Idempotent: a message that already states this trailer is returned unchanged,
    so a re-run and a hand-written `Refs:` do not produce it twice. An existing
    trailer block is joined rather than duplicated, because git only reads the
    last paragraph and a second block would put the first out of reach.
    """
    body = message.rstrip("\n")
    if not body.strip():
        return message
    line = "{}: {}".format(key, value)
    if any(existing.strip() == line for existing in body.splitlines()):
        return message

    paragraphs = body.split("\n\n")
    last = paragraphs[-1].splitlines()
    # A one-paragraph message is a bare title, never a trailer block - and
    # attaching `Refs:` to the title line is exactly the wrong place for it.
    joins_existing = len(paragraphs) > 1 and last and all(
        _TRAILER_LINE_RE.match(existing) for existing in last
    )
    if joins_existing:
        paragraphs[-1] += "\n" + line
    else:
        paragraphs.append(line)
    return "\n\n".join(paragraphs) + "\n"
