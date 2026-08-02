"""The message the tool can write with no network, no key and no model.

Behind a `prepare-commit-msg` hook, an API outage or an expired key would
otherwise be a broken git workflow, which is how a tool gets uninstalled. This
path composes what every run already computes -- the file classes, the workspace
scope, the history's own vocabulary, `git --stat --summary` -- and calls nothing.

What it will not do is guess. `feat:` and `fix:` state *intent*, which no local
signal carries, and a message claiming work that did not happen is the one
failure this product exists to prevent. So the type comes only from what the
file classes prove, and falls to `chore:`, which asserts nothing about
behaviour, the moment they prove nothing.

Pure string work: it takes lists and dicts the caller already has, and never
reads a file or shells out.
"""

from __future__ import annotations

import os

from .files import package_span

# The same ceiling the prompt asks of the model. There is no floor: a commit
# touching one directory gets one bullet, because padding it to two would mean
# inventing the second.
MAX_BULLETS = 6
MAX_TITLE = 72

# Classes that prove the commit is about the build rather than the product. Code
# or a mix is deliberately absent: neither proves anything a type may claim.
_BUILDISH = frozenset(("config", "generated", "vendor", "binary"))


def summary_marks(summary: str) -> tuple:
    """(created paths, deleted paths, how many renames) from `git --summary`.

    Only the three facts a verb can be read off. Renames are counted rather than
    resolved: git writes them as `src/{a.py => b.py}`, and a half-parsed path is
    worse than a count, which is all the verb needs.
    """
    created, deleted, renamed = set(), set(), 0
    for raw in summary.splitlines():
        line = raw.strip()
        if line.startswith("create mode "):
            created.add(_path_after_mode(line))
        elif line.startswith("delete mode "):
            deleted.add(_path_after_mode(line))
        elif line.startswith("rename "):
            renamed += 1
    return created, deleted, renamed


def _path_after_mode(line: str) -> str:
    """The path in `create mode 100644 some/file with spaces.py`."""
    parts = line.split(" ", 3)
    return parts[3] if len(parts) == 4 else ""


def _verb(paths: set, created: set, deleted: set) -> str:
    """What happened to every path in the group, or "Update" when they disagree."""
    if paths and paths <= created:
        return "Add"
    if paths and paths <= deleted:
        return "Remove"
    return "Update"


def offline_type(classes: dict, known=None) -> str:
    """The Conventional Commits type the file classes *prove*, or "" for none.

    Never `feat` and never `fix`: both state intent, and nothing available
    offline can tell an implemented feature from a refactor. `known` is the
    history's own vocabulary -- an empty list means this repo does not prefix
    its subjects at all, and the honest answer there is no prefix.
    """
    if known is not None and not known:
        return ""
    present = set(classes.values())
    chosen = "chore"
    if present == {"docs"}:
        chosen = "docs"
    elif present == {"test"}:
        chosen = "test"
    elif present and present <= _BUILDISH:
        chosen = "build"
    # `chore` even when the history has not used it yet. A repo with any prefix
    # at all uses Conventional Commits, and emitting none there breaks its own
    # convention -- the repo that wants no prefix said so with an empty `known`,
    # which returned above.
    return chosen if not known or chosen in known else "chore"


def offline_scope(files: list, known=None, isfile=os.path.isfile) -> str:
    """The workspace package every staged file shares, or "" when they do not.

    The same `package_span` the online path infers from, so the two can never
    disagree, and the same abstention: files spread across sibling packages get
    no scope rather than one that hides the rest.
    """
    if known is not None and not known:
        return ""
    shared, _roots = package_span(files, isfile)
    return shared.rsplit("/", 1)[-1] if shared else ""


def group_by_directory(files: list) -> list:
    """(directory, its files) in the order git reported them, root as ""."""
    groups: dict = {}
    for path in files:
        directory = os.path.dirname(path.replace("\\", "/"))
        groups.setdefault(directory, []).append(path)
    return list(groups.items())


def offline_subject(files: list, created=(), deleted=(), renamed: int = 0) -> str:
    """The imperative half of the title: what happened, and to how much."""
    if not files:
        return "update the working tree"
    paths = set(files)
    if renamed and renamed == len(files):
        verb = "move"
    else:
        verb = _verb(paths, set(created), set(deleted)).lower()
    if len(files) == 1:
        return f"{verb} {files[0]}"
    groups = group_by_directory(files)
    if len(groups) == 1 and groups[0][0]:
        return f"{verb} {len(files)} files in {groups[0][0]}"
    if len(groups) == 1:
        return f"{verb} {len(files)} files"
    return f"{verb} {len(files)} files across {len(groups)} directories"


def offline_title(
    files: list,
    classes: dict,
    created=(),
    deleted=(),
    renamed: int = 0,
    *,
    types=None,
    scopes=None,
    isfile=os.path.isfile,
) -> str:
    """`type(scope): subject`, within 72 characters."""
    kind = offline_type(classes, types)
    scope = offline_scope(files, scopes, isfile)
    prefix = ""
    if kind:
        prefix = f"{kind}({scope}): " if scope else f"{kind}: "

    subject = offline_subject(files, created, deleted, renamed)
    # A single deeply nested path is the one case that reliably overruns. Its
    # basename still identifies the file, and a clipped path may not.
    if len(prefix) + len(subject) > MAX_TITLE and len(files) == 1:
        subject = f"{subject.split(' ', 1)[0]} {os.path.basename(files[0])}"
    title = prefix + subject
    return title if len(title) <= MAX_TITLE else title[:MAX_TITLE - 3].rstrip() + "..."


def offline_bullets(files: list, created=(), deleted=(), limit: int = MAX_BULLETS) -> list:
    """One bullet per directory, most of them collapsed to a count.

    Grouped rather than listed per file: "3 files under src/api/" is what a
    reader of the log wants, and forty filenames is what they scroll past.
    """
    created, deleted = set(created), set(deleted)
    groups = group_by_directory(files)
    shown = groups if len(groups) <= limit else groups[:limit - 1]

    bullets = []
    for directory, members in shown:
        verb = _verb(set(members), created, deleted)
        if len(members) == 1:
            bullets.append(f"- {verb} {members[0]}")
        else:
            where = f"under {directory}/" if directory else "at the repository root"
            bullets.append(f"- {verb} {len(members)} files {where}")

    rest = groups[len(shown):]
    if rest:
        spare = sum(len(members) for _d, members in rest)
        bullets.append(f"- Update {spare} files under {len(rest)} more directories")
    return bullets


def offline_message(
    files: list,
    classes: dict,
    summary: str = "",
    *,
    title: str | None = None,
    types=None,
    scopes=None,
    isfile=os.path.isfile,
) -> str:
    """The whole message, deterministically, from facts already in hand.

    `title` is the author's own `-m`, which wins here exactly as it does online:
    they know the intent this path is careful never to guess at.
    """
    created, deleted, renamed = summary_marks(summary)
    head = title if title else offline_title(
        files, classes, created, deleted, renamed,
        types=types, scopes=scopes, isfile=isfile,
    )
    bullets = offline_bullets(files, created, deleted)
    if not bullets:
        return head + "\n"
    return head + "\n\n" + "\n".join(bullets) + "\n"
