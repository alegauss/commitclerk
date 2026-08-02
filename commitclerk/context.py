"""What the author knows and the diff cannot show.

Two shapes, because intent arrives in two. `--context "<note>"` is the one-off:
why this change, this once. `.clerk/context.md` is the standing fact - the
product's name, which binary the CLI installs as, that `docs/` is internal - true
of every commit in the repository and therefore not worth retyping.

Both are strictly additive to the prompt, and neither can change what the tool
does. That is the whole safety argument: the worst a bad context file can do is
waste part of the diff budget.
"""

from __future__ import annotations

import os

# under the repository root, beside `.clerk.json`. Spelled with a forward slash
# because it is shown to the user in `--help` and written that way in every
# document; Windows opens it just the same.
CONTEXT_FILE = ".clerk/context.md"

# A few lines, as documented. Generous enough for a paragraph of standing facts
# and far too small to be a second README - which is the point, because every
# character here is a character of diff the model does not see.
MAX_CONTEXT_CHARS = 2_000


def context_path(root: str | None) -> str | None:
    """`<repo root>/.clerk/context.md`, or None outside a repository."""
    return os.path.normpath(os.path.join(root, CONTEXT_FILE)) if root else None


def read_context_file(path: str | None) -> str:
    """The standing context, or "" when there is no readable file.

    Unlike the config file this never raises: a config file states what the tool
    must do, so a broken one has to stop it, while this only adds a paragraph to
    a prompt. Failing a commit over an unreadable note would be the wrong trade.
    """
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError):
        return ""
    return text.strip()


def context_note(standing: str = "", one_off: str = "",
                 limit: int = MAX_CONTEXT_CHARS) -> str:
    """The prompt block for both kinds of context, or "" when there is neither.

    The one-off note comes last because it is about *this* commit, and it is
    given the whole budget first: a standing file is a convenience, but the note
    the author typed for this run is the thing they most expect to be honoured.
    """
    one_off = (one_off or "").strip()
    standing = (standing or "").strip()
    if not one_off and not standing:
        return ""

    one_off = one_off[:limit]
    standing = standing[:max(0, limit - len(one_off))]

    lines = [
        "Context from the author (facts the diff cannot show; use it to explain "
        "WHY, never restate it as work this commit did):",
    ]
    if standing:
        lines += ["", standing]
    if one_off:
        lines += ["", "About this change specifically: " + one_off]
    return "\n".join(lines)
