"""`.clerkignore`: the files whose contents are never transmitted.

A repository with three sensitive files should not have to refuse the tool
outright. This turns the decision from per-repository into per-file: a matched
path keeps its diff header and its line counts, and loses its body.

**The path is still sent.** Only contents are withheld, and any claim otherwise
would be a false assurance. A team that cannot disclose a *filename* wants
`--offline`, or not to run the tool there at all.

`.gitignore` semantics over a documented subset. Syntax outside it is an error
rather than a pattern that matches nothing, because a rule that quietly does
nothing is a file quietly transmitted.
"""

from __future__ import annotations

import os
import re
from typing import NamedTuple

from .config import ConfigError

CLERKIGNORE = ".clerkignore"
# How many paths the notice names before summarising. Enough to recognise the
# list, not enough to bury the run's real output.
MAX_NAMED = 5


class Rule(NamedTuple):
    """One line of `.clerkignore`, compiled."""

    regex: object
    negated: bool
    source: str
    line: int


def clerkignore_path(root: str | None) -> str | None:
    """`<repo root>/.clerkignore`, or None outside a repository.

    The root and not the working directory, exactly as `.clerk.json` is found:
    which subdirectory you are standing in must never change what is withheld.
    """
    return os.path.normpath(os.path.join(root, CLERKIGNORE)) if root else None


def _translate(pattern: str) -> str:
    """A glob as a regex fragment, where `*` stops at a `/` and `**` does not."""
    out = []
    i, size = 0, len(pattern)
    while i < size:
        char = pattern[i]
        if char == "*":
            if pattern[i:i + 3] == "**/":
                out.append("(?:.*/)?")
                i += 3
                continue
            if pattern[i:i + 2] == "**":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            close = pattern.find("]", i + 1)
            if close == -1:
                out.append(re.escape(char))
            else:
                body = pattern[i + 1:close]
                out.append("[" + ("^" + body[1:] if body.startswith("!") else body) + "]")
                i = close + 1
                continue
        else:
            out.append(re.escape(char))
        i += 1
    return "".join(out)


def compile_pattern(pattern: str, line: int = 0) -> Rule:
    """One pattern as a `Rule` matching POSIX, repository-relative paths."""
    source = pattern
    negated = pattern.startswith("!")
    if negated:
        pattern = pattern[1:]

    directory_only = pattern.endswith("/")
    pattern = pattern.rstrip("/")

    anchored = pattern.startswith("/")
    if anchored:
        pattern = pattern[1:]
    elif "/" in pattern:
        # `docs/x.md` is anchored to the root; a bare `x.md` matches at any
        # depth. That asymmetry is `.gitignore`'s, and people already know it.
        anchored = True

    prefix = "" if anchored else "(?:.*/)?"
    # A bare name may be a directory, so it also matches everything beneath it.
    suffix = "/.*" if directory_only else "(?:/.*)?"
    return Rule(
        re.compile("^" + prefix + _translate(pattern) + suffix + "$"),
        negated,
        source,
        line,
    )


def parse_clerkignore(text: str, path: str = CLERKIGNORE) -> list:
    """The rules in `text`, in file order, or ConfigError naming the line.

    Refusing beats ignoring. Every rule here is one a person wrote to keep
    something off the wire, so a line this subset cannot honour has to stop the
    run -- silently matching nothing is the one outcome they would not accept.
    """
    rules = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "\\" in line:
            raise ConfigError(
                f"{path}:{number}: use forward slashes - '\\' is a separator here, "
                "not an escape"
            )
        if line.lstrip("!").strip("/") == "":
            raise ConfigError(f"{path}:{number}: '{line}' matches nothing")
        rules.append(compile_pattern(line, number))
    return rules


def read_clerkignore(path: str | None) -> list:
    """The rules in `path`, or [] when there is no such file."""
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}")
    return parse_clerkignore(text, path)


def excluded(path: str, rules: list) -> bool:
    """Whether `path` is withheld, the last matching rule winning.

    Last and not first, so `!` can carve an exception out of a broad rule above
    it -- which is the order `.gitignore` uses and the only one in which
    negation means anything.
    """
    posix = path.replace("\\", "/")
    verdict = False
    for rule in rules:
        if rule.regex.match(posix):
            verdict = not rule.negated
    return verdict


def excluded_paths(files: list, rules: list) -> list:
    """The staged files `.clerkignore` withholds, in the order git reported them."""
    return [path for path in files if excluded(path, rules)] if rules else []


def exclusion_notice(paths: list) -> str:
    """What to print when something was withheld, or "" when nothing was.

    It names what was *not* sent and, in the same breath, what still was. A
    notice that only mentioned the first would be read as the guarantee this
    feature is careful not to give.
    """
    if not paths:
        return ""
    count = len(paths)
    named = ", ".join(paths[:MAX_NAMED])
    if count > MAX_NAMED:
        named += f", and {count - MAX_NAMED} more"
    subject = "1 file" if count == 1 else f"{count} files"
    return (
        f"Note: {subject} excluded by {CLERKIGNORE}; the contents were not sent "
        f"({named}). The paths and line counts were."
    )
