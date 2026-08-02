#!/usr/bin/env python
# ---------------------------------------------------------------------------
# GENERATED FILE - do not edit.
#
# This is the `commitclerk` package concatenated into a single script by
# `scripts/build_single_file.py`. Edit the package under `commitclerk/` and
# rebuild; CI fails if this file is out of date.
#
# It exists so the tool stays one readable, dependency-free file you can audit
# and copy:
#
#     curl -O https://raw.githubusercontent.com/alegauss/commitclerk/main/dist/commitclerk.py
#     python commitclerk.py --help
# ---------------------------------------------------------------------------

"""commitclerk - AI-powered git commit messages.

Generates a commit message (short imperative title + bulleted summary body)
from the staged diff by calling an LLM provider.

Reads the API key from the provider's key variable (OPENAI_API_KEY for the
default provider). No third-party dependencies.

Usage (installed as `clerk`, `commitclerk` or `git clerk`, or run the
single-file build with `python commitclerk.py`):
    clerk                       # AI writes the whole message
    clerk -m "docs: fix X"      # use this exact title; AI writes only the body
    clerk --dry-run             # print message, do not commit
    clerk --model gpt-4o-mini
    clerk --provider anthropic  # select the API provider
    clerk --provider ollama     # local model, no API key, nothing leaves the box
    clerk --timeout 180         # give a slow local model more room
    clerk --deep                # summarize each file too big for the budget
    clerk --base-url http://localhost:11434/v1   # any OpenAI-compatible endpoint
    clerk --no-house-style      # do not copy this repo's own commit conventions
    clerk --no-examples         # keep the fingerprint, send no past message text
    clerk --redact              # mask a staged secret instead of refusing to send
    clerk --offline             # no API call at all: a local, deterministic draft
    clerk --context "reverts the caching experiment"   # why, in one sentence
    git clerk                   # same tool, as a native git subcommand

Environment:
    OPENAI_API_KEY      required by the openai provider
    OPENAI_MODEL        optional, overrides the openai provider's default model
    OPENAI_BASE_URL     optional, overrides the endpoint (Ollama, vLLM, Azure, ...)
    ANTHROPIC_API_KEY   required by the anthropic provider
    ANTHROPIC_MODEL     optional, overrides the anthropic provider's default model
    ANTHROPIC_BASE_URL  optional, overrides the anthropic endpoint
    OLLAMA_MODEL        optional, overrides the ollama provider's default model
    OLLAMA_BASE_URL     optional, overrides the ollama endpoint
    CLERK_PROVIDER      optional, selects the provider (default: openai)

Configuration files (JSON; keys provider, model, base_url, timeout, max_chars,
house_style, examples, scan, deep, ticket_refs, ticket_pattern). A setting is
taken from the first place that has it:
    a flag  >  the environment  >  ./.clerk.json  >  ~/.config/clerk/config.json
    >  the built-in default
`.clerk.json` is looked for at the repository root, so the tool behaves the same
from any subdirectory, and is meant to be committed: it is how a team stops
retyping its own convention. API keys are read from the environment only.

`.clerkignore` at the repository root withholds the *contents* of the paths it
matches (`.gitignore` syntax): they reach the model as a header and a line count
only. The paths themselves are still sent - see `excludes.py`.

`.clerk/context.md` under the repository root carries standing facts the diff
cannot show, read verbatim on every run; `--context "<note>"` says the same
thing for one commit. Both only add to the prompt - see `context.py`.

With ticket_refs on, the issue key in the branch name (feat/PROJ-123-thing)
is appended to the finished message as a `Refs: PROJ-123` trailer. Off by
default, and never sent to the model - see `trailers.py`.

Why the doc-only handling: this tool only sees the staged diff, so when a
commit just adds prose to CHANGELOG/ROADMAP/README that *describes* a feature,
the model used to echo it as "feat: implement <feature>" even though the feature
shipped in an earlier commit. The rules in `prompt.py` (and the -m override)
keep the message about what THIS commit actually changes.

`history.py` reads the last 200 commit subjects, bodies and touched paths: it
measures the types, scopes, body shape and language this repo actually uses, and
picks the past commits that overlap the current diff as worked examples, so the
message written belongs in this history rather than being generically correct.
`files.py` walks
each staged file up to its nearest workspace manifest, so a monorepo change
confined to one package is scoped to it.

For a commit no budget can fit, `--deep` (`deep.py`) summarizes each oversized
file in its own cheap request and writes the message from those summaries plus
the smaller files' real diffs, so the tail of a 5 000-line change is described
rather than trimmed away. One extra request per oversized file, none when the
diff already fits, and a summary that fails leaves that file to be trimmed as
usual - never invented.

`secrets.py` reads the staged diff's added lines before any request is made and
refuses (exit 3) when a line carries a known credential shape or a high-entropy
token, naming the file, the line and the detector but never the match. `--redact`
masks them in the request instead; the commit still contains them. `--no-scan`
or `"scan": false` turns it off.

`offline.py` writes the message with no key, no network and no model when
`--offline` is passed: the type from the file classes, the scope from the
workspace manifest, bullets grouped by directory. It never emits feat: or fix:,
which state intent no local signal carries, so it is a draft rather than a
replacement - and it beats an error at the moment someone is trying to commit.

The source is a package; `dist/commitclerk.py` is the same code concatenated into
one file by `scripts/build_single_file.py`, for people who would rather read and
copy a single script than install anything.
"""

from __future__ import annotations

from collections import Counter
from typing import NamedTuple
import argparse
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request

__version__ = "0.2.1"


# --- from commitclerk/config.py ---------------------------------------

PROJECT_CONFIG = ".clerk.json"
# under the user's `~/.config`, which is where the second half of the path lives.
USER_CONFIG = ("clerk", "config.json")

# name -> the type the value must have. A key absent from this table is a key
# this version does not know: it is reported and ignored, so a config written
# for a later release does not stop an earlier one from committing.
SETTINGS = {
    "provider": str,
    "model": str,
    "base_url": str,
    "timeout": int,
    "max_chars": int,
    "house_style": bool,
    # The narrow half of `house_style`: the fingerprint is counts and shapes, the
    # examples are past commit message text verbatim, and a team can refuse the
    # second while keeping the first. `"house_style": false` still refuses both.
    "examples": bool,
    # On unless a file turns it off, unlike every other switch here: the scan is
    # the one setting whose default has to be the safe answer, because the cost of
    # being wrong is a credential at a third party and is not reversible.
    "scan": bool,
    # Off unless asked for: it spends one extra request per oversized file, and a
    # setting that multiplies a bill has no business defaulting to on.
    "deep": bool,
    # Off unless a project asks for it: a `Refs:` trailer on a repository with no
    # tracker is noise, and this tool does not add ceremony to other people's
    # history uninvited. Setting `ticket_pattern` turns it on too.
    "ticket_refs": bool,
    "ticket_pattern": str,
}

_TYPE_NAMES = {str: "a string", int: "a whole number", bool: "true or false"}


class ConfigError(Exception):
    """A file the user wrote that cannot be honoured exactly as written."""


def user_config_path(home: str | None = None) -> str:
    return os.path.join(home if home is not None else os.path.expanduser("~"),
                        ".config", *USER_CONFIG)


def project_config_path(root: str | None) -> str | None:
    """`<repo root>/.clerk.json`, or None outside a repository.

    The root, not the working directory: which subdirectory you happen to be
    standing in must not change what the tool does. Normalised because git
    reports the root with forward slashes even on Windows, and the path is shown
    to the user in every message about this file.
    """
    return os.path.normpath(os.path.join(root, PROJECT_CONFIG)) if root else None


def env_value(name: str | None) -> str | None:
    """An environment variable, or None when it is unset *or* empty.

    An exported-but-empty variable is how a shell says "not set". Letting "" win
    the ladder would call the API with an empty model name.
    """
    return (os.environ.get(name) if name else None) or None


def read_config(path: str | None) -> tuple[dict, list[str]]:
    """(values, notices) for `path`, or ({}, []) when there is no such file.

    Raises ConfigError for a file that exists and cannot be honoured. A syntax
    error or a wrongly typed value is not something to route around: the user
    wrote the file to change the tool's behaviour, and quietly doing something
    else is the failure this project exists to avoid.
    """
    if not path or not os.path.isfile(path):
        return {}, []
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    # ValueError covers both JSONDecodeError and the UnicodeDecodeError a file
    # that is not really UTF-8 raises on read.
    except (OSError, ValueError) as exc:
        raise ConfigError("cannot read {}: {}".format(path, exc))
    if not isinstance(data, dict):
        raise ConfigError("{} must contain a JSON object".format(path))

    values: dict = {}
    notices: list[str] = []
    for key in sorted(data):
        expected = SETTINGS.get(key)
        if expected is None:
            notices.append("Note: unknown setting '{}' in {}, ignored.".format(key, path))
            continue
        value = data[key]
        # `bool` is a subclass of `int` in Python, so an int setting has to turn
        # `true` away by hand or `"timeout": true` would mean a one-second timeout.
        if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            raise ConfigError("{}: '{}' must be {}".format(path, key, _TYPE_NAMES[expected]))
        values[key] = value
    return values, notices


def load_config(root: str | None, home: str | None = None) -> tuple[dict, dict, list[str]]:
    """(project, user, notices) - both files, read and kept apart.

    Unmerged on purpose: the ladder puts the environment above one of them and
    nothing above the other, so merging here would be a second precedence rule.
    """
    project, project_notices = read_config(project_config_path(root))
    user, user_notices = read_config(user_config_path(home))
    return project, user, project_notices + user_notices


def layered(cli, env, project, user, default):
    """CLI > environment > project file > user file > built-in default.

    The only place that order exists. Every setting hands over its five
    candidates in it, so a new setting cannot quietly invent a different one.
    `None` alone means "not set at this layer" - a `false` or `0` written on
    purpose is honoured, which is why this is not a chain of `or`.
    """
    for value in (cli, env, project, user, default):
        if value is not None:
            return value
    return None


# --- from commitclerk/context.py --------------------------------------

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


# --- from commitclerk/excludes.py -------------------------------------

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


# --- from commitclerk/diffing.py --------------------------------------

MAX_DIFF_CHARS = 60_000
# them, so sending thousands of lines only crowds out the files that matter.
DEMOTED_CLASSES = ("generated", "vendor")
# ...but only once the body is big enough to be worth replacing. A two-line lockfile
# bump costs nothing, and a placeholder would be longer than the content.
DEMOTE_MIN_CHARS = 500

def truncate(diff: str, limit: int) -> str:
    if len(diff) <= limit:
        return diff
    return diff[:limit] + "\n\n[...diff truncated for context length...]"


# Room set aside per file for its own "[... N lines truncated ...]" marker, so
# the markers can never push the result past the caller's limit.
_MARKER_RESERVE = 40


def split_diff(diff: str) -> list[str]:
    """Split a unified diff into one chunk per file, in the original order."""
    chunks: list[str] = []
    current: list[str] = []
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git ") and current:
            chunks.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("".join(current))
    return chunks


def _split_header(chunk: str) -> tuple[list[str], list[str]]:
    """Separate a file chunk's header (up to the first hunk) from its body."""
    lines = chunk.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("@@"):
            return lines[:i], lines[i:]
    return lines, []


def chunk_path(chunk: str) -> str | None:
    """The file a diff chunk is about, taken from its `diff --git a/x b/x` header.

    The b-side is used, so a rename reports its new name.
    """
    first = chunk.split("\n", 1)[0]
    if not first.startswith("diff --git "):
        return None
    parts = first.split(" b/", 1)
    return parts[1].strip() or None if len(parts) == 2 else None


def count_changes(chunk: str) -> tuple[int, int]:
    """Added and removed line counts for one diff chunk."""
    added = removed = 0
    for line in chunk.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed


def doc_line_share(diff: str) -> float | None:
    """Fraction of the commit's changed lines that live in documentation files."""
    doc_lines = total = 0
    for chunk in split_diff(diff):
        path = chunk_path(chunk)
        changed = sum(count_changes(chunk))
        total += changed
        if path and _is_doc(path):
            doc_lines += changed
    return doc_lines / total if total else None


def doc_guard_note(files: list[str], diff: str = "") -> str:
    """The caution about documentation prose for this commit, or "" if none applies.

    Three cases, not two. All documentation is the easy one. The dangerous one is
    *mixed*: a 900-line CHANGELOG entry plus a one-line typo fix used to switch the
    guard off entirely and come back as "feat: implement <the feature the changelog
    describes>" — the exact failure this tool exists to prevent.
    """
    docs = [f for f in files if _is_doc(f)]
    if not docs:
        return ""
    if len(docs) == len(files):
        return _DOC_ONLY_NOTE
    share = doc_line_share(diff)
    share_text = ""
    if share is not None and share >= 0.5:
        # Capped at 99: code is present by definition here, so rounding 900/901 up
        # to "100% of the changed lines" would contradict the sentence before it.
        share_text = (
            f" Documentation is {min(99, round(share * 100))}% of the changed lines, "
            "so the commit is mostly a documentation edit."
        )
    return _MIXED_DOCS_NOTE.format(files=", ".join(docs), share=share_text)


def demote_diff(
    diff: str,
    classes: dict,
    classes_to_demote: tuple = DEMOTED_CLASSES,
    excluded=(),
) -> str:
    """Replace the body of files that can never be the subject with one line.

    A `package-lock.json` bump is thousands of lines the model has been told not to
    narrate, competing for the same budget as the three-line fix that is the actual
    commit. The header stays — silently dropping a file would repeat the mistake
    head-truncation used to make — and the counts stay, because "regenerated the
    lockfile (+8412 -3110)" is the whole of what a reader needs.

    `excluded` is `.clerkignore`'s answer and obeys neither rule above: no class
    qualifies it and `DEMOTE_MIN_CHARS` does not apply, because a three-line
    `.env` is exactly the case that file exists for.
    """
    if not classes and not excluded:
        return diff
    out = []
    for chunk in split_diff(diff):
        path = chunk_path(chunk)
        klass = classes.get(path) if path else None
        header, body = _split_header(chunk)
        body_text = "".join(body)
        hidden = path in excluded if path else False
        if hidden or (klass in classes_to_demote and len(body_text) > DEMOTE_MIN_CHARS):
            added, removed = count_changes(body_text)
            what = "excluded by .clerkignore" if hidden else f"{klass} file"
            out.append(
                "".join(header)
                + f"[... {what}, +{added} -{removed}, contents not shown ...]\n"
            )
        else:
            out.append(chunk)
    return "".join(out)


def _allocate_round_robin(bodies: list[list[str]], remaining: int) -> list[int]:
    """How many leading lines of each body fit, handing out one line at a time."""
    taken = [0] * len(bodies)
    done = [not body for body in bodies]
    while remaining > 0 and not all(done):
        for i, body in enumerate(bodies):
            if done[i]:
                continue
            cost = len(body[taken[i]]) if taken[i] < len(body) else remaining + 1
            if cost > remaining:
                done[i] = True
                continue
            taken[i] += 1
            remaining -= cost
    return taken


def _headers_and_bodies(chunks: list[str]) -> tuple[list[list[str]], list[list[str]]]:
    headers, bodies = [], []
    for chunk in chunks:
        header, body = _split_header(chunk)
        headers.append(header)
        bodies.append(body)
    return headers, bodies


def _shares(headers: list[list[str]], bodies: list[list[str]], limit: int) -> list[int]:
    reserved = sum(len("".join(h)) + _MARKER_RESERVE for h in headers)
    return _allocate_round_robin(bodies, limit - reserved)


def over_budget_paths(diff: str, limit: int) -> list[str]:
    """The files `budget_diff` would have to cut, in diff order.

    Asked *before* the trim, because "which files does the model never see the
    end of" is the only question worth asking of a commit no budget can fit —
    and the honest answer is the one the allocator itself would give. A file
    named here is a file whose tail would otherwise go undescribed.
    """
    if len(diff) <= limit:
        return []
    chunks = split_diff(diff)
    if len(chunks) <= 1:
        # One file over budget: head-truncation is about to eat its tail, and
        # there is no allocation to consult.
        path = chunk_path(chunks[0]) if chunks else None
        return [path] if path else []

    headers, bodies = _headers_and_bodies(chunks)
    taken = _shares(headers, bodies, limit)
    out = []
    for i, chunk in enumerate(chunks):
        path = chunk_path(chunk) if taken[i] < len(bodies[i]) else None
        if path:
            out.append(path)
    return out


def budget_diff(diff: str, limit: int) -> str:
    """Fit `diff` into `limit` chars while keeping every file visible.

    Head-truncation hides whole files: `git diff` orders by path, not by
    importance, so cutting at N characters can drop the very files the commit
    was about. Instead every file keeps its header, and the remaining budget is
    handed out **round-robin** one line at a time — proportional shares would
    just reproduce the same bias towards large files.
    """
    if len(diff) <= limit:
        return diff

    chunks = split_diff(diff)
    if len(chunks) <= 1:
        # One file: there is nothing to be fair between.
        return truncate(diff, limit)

    headers, bodies = _headers_and_bodies(chunks)
    taken = _shares(headers, bodies, limit)

    out = []
    for i in range(len(chunks)):
        text = "".join(headers[i] + bodies[i][:taken[i]])
        dropped = len(bodies[i]) - taken[i]
        if dropped:
            if text and not text.endswith("\n"):
                text += "\n"
            text += f"[... {dropped} lines truncated ...]\n"
        out.append(text)

    result = "".join(out)
    # Only reachable when the headers alone overrun the budget (a commit with a
    # very large number of files); the caller's limit still wins.
    return result if len(result) <= limit else truncate(result, limit)


# --- from commitclerk/deep.py -----------------------------------------

# What one file may show its summarizer. The same number as the whole-commit
# default, which is the point: a file too big to share a budget is given one.
SUMMARY_INPUT_CHARS = 60_000

# Two lines, as commissioned. A summarizer that writes an essay is spending the
# budget the summary exists to save, so the cap is enforced here rather than
# hoped for in the prompt.
SUMMARY_MAX_LINES = 2
SUMMARY_LINE_CHARS = 220

# Marks a summarized line inside the diff. Unmistakable on sight, and the note
# below tells the model what it means -- a summary that read like diff content
# would be prose the model could mistake for the file's own text.
SUMMARY_MARK = "[summary] "

SUMMARY_SYSTEM_PROMPT = (
    "You summarize the diff of ONE file from a large commit, for another model that "
    "will write the commit message and will never see this diff.\n\n"
    "Rules:\n"
    "- At most two lines of plain prose. No bullets, no markdown, no code fences.\n"
    "- Say what changed in this file: the behaviour, the structure, the intent. Not a "
    "line-by-line replay, and not the file name, which the reader already has.\n"
    "- Only what this diff shows. Never guess at the rest of the commit, and never "
    "mention files you were not given.\n"
    "- If the change is prose added to documentation, say that the documentation was "
    "edited and what it now covers. Never restate documented features as work this "
    "commit implemented.\n"
    "- If nothing meaningful changed (whitespace, reformatting, a mechanical rename), "
    "say exactly that in one line."
)

# Sits with the diff it describes, because it is the key to a notation that
# appears inside it.
DEEP_NOTE = (
    "Some files were too large to include. Their diff body is replaced by lines marked "
    "[summary], each written by a reader that saw that file's complete diff. Treat a "
    "[summary] line as an accurate account of what changed in that file and weigh it "
    "exactly as you weigh the files whose real diff is shown."
)


def summary_user_prompt(path: str, chunk: str, limit: int = SUMMARY_INPUT_CHARS) -> str:
    """The request for one file's summary."""
    return "\n".join([f"File: {path}", "", "Unified diff for this file:", truncate(chunk, limit)])


def clean_summary(
    text: str,
    max_lines: int = SUMMARY_MAX_LINES,
    line_chars: int = SUMMARY_LINE_CHARS,
) -> list[str]:
    """The usable lines of a summarizer's answer, stripped of any formatting.

    The prompt asks for two plain lines; models answer with bullets, fences and
    a preamble anyway. Everything downstream depends on this being short, so it
    is cut here instead of being asked for twice.
    """
    lines = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("```"):
            continue
        line = line.lstrip("-*#> ").strip()
        if not line:
            continue
        lines.append(line[:line_chars])
        if len(lines) >= max_lines:
            break
    return lines


def summary_block(chunk: str, lines: list[str]) -> str:
    """One file's header, the counts, and its summary in place of its body.

    Shaped like `demote_diff`'s placeholder on purpose: the header survives, the
    counts survive, and what is missing says so. The difference is that this one
    knows what was in there.
    """
    header, body = _split_header(chunk)
    added, removed = count_changes("".join(body))
    out = "".join(header)
    if out and not out.endswith("\n"):
        out += "\n"
    out += f"[... file too large to show, +{added} -{removed}, summarized below ...]\n"
    return out + "".join(SUMMARY_MARK + line + "\n" for line in lines)


def summarize_diff(diff: str, paths: list[str], summarize) -> tuple[str, int]:
    """`diff` with each named file's body replaced by a summary, and how many.

    `summarize(path, chunk)` returns the model's text for one file, or "" when
    it could not be had. An empty answer leaves the real body alone, to be
    trimmed as it would have been: a file with no summary is a budget problem,
    and a summary the tool made up instead would be the one failure this tool
    exists to prevent.
    """
    wanted = set(paths)
    if not wanted:
        return diff, 0

    out = []
    done = 0
    for chunk in split_diff(diff):
        path = chunk_path(chunk)
        lines = clean_summary(summarize(path, chunk)) if path in wanted else []
        if lines:
            out.append(summary_block(chunk, lines))
            done += 1
        else:
            out.append(chunk)
    return "".join(out), done


# --- from commitclerk/files.py ----------------------------------------

# A commit touching ONLY these counts as documentation-only: it gets a docs:
# prefix and a framing that describes the doc change itself.
_DOC_SUFFIXES = (".md", ".mdx", ".rst", ".txt", ".adoc")
_DOC_BASENAMES = {
    "changelog", "readme", "roadmap", "agents", "license",
    "contributing", "authors", "notice", "codeowners",
}


def _is_doc(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    base = p.rsplit("/", 1)[-1]
    stem = base.split(".", 1)[0]
    if p.endswith(_DOC_SUFFIXES):
        return True
    if p.startswith("docs/") or "/docs/" in p:
        return True
    return stem in _DOC_BASENAMES


# The taxonomy that generalises _is_doc. Order matters: the first match wins, and
# vendored or generated files are classified as such even when they look like code.
_VENDOR_DIRS = ("vendor/", "third_party/", "third-party/", "node_modules/",
                "site-packages/", ".venv/", "external/")
_GENERATED_DIRS = ("dist/", "build/", "__snapshots__/", "migrations/", "generated/")
_GENERATED_BASENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock",
    "cargo.lock", "gemfile.lock", "composer.lock", "go.sum", "flake.lock",
}
_GENERATED_SUFFIXES = (".lock", ".snap", ".map", ".po", ".mo", "_pb2.py", ".pb.go")
_TEST_DIRS = ("tests/", "test/", "spec/", "__tests__/", "e2e/")
_TEST_SUFFIXES = (".spec.js", ".spec.ts", ".spec.tsx", ".test.js", ".test.ts",
                  ".test.tsx", "_test.py", "_test.go", "_test.rb", "test.java")
_CONFIG_DIRS = (".github/", ".circleci/", ".vscode/", ".idea/")
_CONFIG_BASENAMES = {
    "pyproject.toml", "setup.py", "setup.cfg", "package.json", "tsconfig.json",
    "makefile", "dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "requirements.txt", "gemfile", "cargo.toml", "go.mod", "pom.xml", "build.gradle",
}
_CONFIG_SUFFIXES = (".toml", ".ini", ".cfg", ".yml", ".yaml", ".editorconfig")

FILE_CLASSES = ("vendor", "generated", "binary", "docs", "test", "config", "code")


def _has_segment(path: str, prefixes: tuple) -> bool:
    """Whether any path segment starts one of `prefixes` (e.g. 'tests/')."""
    return any(path.startswith(p) or f"/{p}" in path for p in prefixes)


def classify(path: str, binaries: set | None = None) -> str:
    """The class of one staged file: vendor, generated, binary, docs, test, config, code.

    A boolean "is this documentation?" was enough for one guard. A class per file
    is what tells the model which files are the *point* of the commit and which are
    noise it must not narrate. `binaries` comes from `binary_paths(diff)`, since a
    path alone cannot tell you whether git could read the contents.
    """
    binary = bool(binaries) and path in binaries
    p = path.replace("\\", "/").lower()
    base = p.rsplit("/", 1)[-1]

    if _has_segment(p, _VENDOR_DIRS):
        return "vendor"
    if base in _GENERATED_BASENAMES or p.endswith(_GENERATED_SUFFIXES) \
            or _has_segment(p, _GENERATED_DIRS):
        return "generated"
    if binary:
        return "binary"
    if _is_doc(path):
        return "docs"
    if _has_segment(p, _TEST_DIRS) or base.startswith("test_") or p.endswith(_TEST_SUFFIXES):
        return "test"
    if _has_segment(p, _CONFIG_DIRS) or base in _CONFIG_BASENAMES \
            or p.endswith(_CONFIG_SUFFIXES) or base.startswith("."):
        return "config"
    return "code"


def binary_paths(diff: str) -> set:
    """Paths git could not diff as text, read off the diff's own binary markers."""
    found = set()
    current = None
    for line in diff.splitlines():
        if line.startswith("diff --git a/"):
            # "diff --git a/x b/x" — take the b-side, which is the new name.
            parts = line.split(" b/", 1)
            current = parts[1] if len(parts) == 2 else None
        elif current and (line.startswith("Binary files ") or line == "GIT binary patch"):
            found.add(current)
    return found


def classify_files(files: list[str], diff: str = "") -> dict:
    """Every staged file mapped to its class, in the order git reported them."""
    binaries = binary_paths(diff) if diff else set()
    return {f: classify(f, binaries) for f in files}


def class_mix(classes: dict) -> str:
    """A compact count per class, most significant first: 'code 3, test 1'."""
    counts = [(c, sum(1 for v in classes.values() if v == c)) for c in FILE_CLASSES]
    return ", ".join(f"{name} {n}" for name, n in counts if n)


def is_doc_only(files: list[str]) -> bool:
    return bool(files) and all(classify(f) == "docs" for f in files)

_DOC_ONLY_NOTE = (
    "IMPORTANT: every file in this commit is documentation (no code changed). "
    "Use the docs: prefix and describe the documentation change itself "
    "(e.g. 'document X', 'record X in the changelog', 'remove completed tasks from the roadmap', "
    "'correct stale claims in README'). Do NOT say a feature was implemented or added: any feature "
    "described in the diff shipped in an earlier commit; this commit only writes it down."
)

# The same caution for the far more common mixed commit. It cannot simply say "do
# not describe a feature as implemented" — sometimes the code really does implement
# it — so it ties the claim to the non-documentation part of the diff.
_MIXED_DOCS_NOTE = (
    "IMPORTANT - how to read this commit: it changes documentation ({files}) alongside "
    "non-documentation files.{share} Prose added to documentation usually describes work "
    "that shipped in EARLIER commits, so it is NOT evidence that this commit implements "
    "anything. Decide the type prefix ONLY from the non-documentation diff lines: use "
    "feat: if they add behaviour, fix: if they fix behaviour, and if they are trivial "
    "(a comment, a docstring, formatting, a rename) then this is a documentation commit - "
    "use docs: and make the documentation change the subject. Never restate a feature "
    "named in the prose as work done in this commit."
)


# A directory holding one of these is a workspace package: the unit a monorepo's
# Conventional Commits scope names. The list is deliberately short — a false
# positive invents a scope, which is worse than emitting none.
_MANIFESTS = (
    "package.json", "pyproject.toml", "setup.py", "pom.xml", "go.mod", "Cargo.toml",
    "build.gradle", "build.gradle.kts", "composer.json", "Gemfile", "mix.exs",
)


def package_root(path: str, isfile=os.path.isfile) -> str | None:
    """The nearest ancestor directory of `path` holding a workspace manifest.

    Nearest, not outermost, so a monorepo's root `package.json` (the one that only
    declares `workspaces`) never wins over the package the file actually lives in.
    The repository root can never be returned: a single-package repo would get its
    own checkout directory as a scope, and `feat(commitclerk): ...` in commitclerk
    is noise, not information.
    """
    parts = path.replace("\\", "/").split("/")[:-1]
    while parts:
        directory = "/".join(parts)
        if any(isfile(f"{directory}/{manifest}") for manifest in _MANIFESTS):
            return directory
        parts.pop()
    return None


def package_span(files: list[str], isfile=os.path.isfile) -> tuple:
    """(the one package containing every staged file, every package they touch).

    The first element is None when the files are spread across sibling packages —
    `packages/api` and `packages/web` have no package in common, and `packages/` is
    not one. A package that is an ancestor of all the others *is* returned, so a
    change inside a package and a nested sub-package still scopes to the outer one.
    """
    roots: list[str] = []
    for path in files:
        root = package_root(path, isfile)
        if root and root not in roots:
            roots.append(root)
    if not roots:
        return None, []
    shortest = min(roots, key=len)
    shared = shortest if all(
        r == shortest or r.startswith(shortest + "/") for r in roots
    ) else None
    return shared, roots


def _package_names(roots: list[str], limit: int = 5) -> str:
    names = sorted(root.rsplit("/", 1)[-1] for root in roots)
    shown = ", ".join(names[:limit])
    return shown + f", and {len(names) - limit} more" if len(names) > limit else shown


def scope_note(files: list[str], known_scopes=None, isfile=os.path.isfile) -> str:
    """The Conventional Commits scope these files imply, as a prompt line.

    `feat: add retry` in a forty-package monorepo is nearly useless and
    `feat(billing-api): add retry` is not, but the wrong scope is worse than none:
    naming one package when the commit touched three hides two of them. So the
    inference is deterministic and it abstains loudly.

    `known_scopes` is the scope vocabulary observed in the repo's history (see
    `history.house_style`). An empty — not absent — vocabulary means the history
    was read and this repo does not use scopes at all, which is an instruction to
    stay quiet rather than an invitation to start.
    """
    if known_scopes is not None and not known_scopes:
        return ""
    shared, roots = package_span(files, isfile)
    if shared:
        scope = shared.rsplit("/", 1)[-1]
        note = (
            f"Scope: '{scope}' - every staged file lives in the workspace package "
            f"{shared}. Put it in the Conventional Commits prefix, e.g. 'fix({scope}): ...'."
        )
        if known_scopes and scope not in known_scopes:
            note += " This repo's history has not used that scope before."
        return note
    if len(roots) > 1:
        return (
            f"Scope: the staged files span {len(roots)} workspace packages "
            f"({_package_names(roots)}). Do NOT scope the message to one of them - that "
            "would hide the rest. Omit the scope, or name what they have in common."
        )
    return ""


def doc_line_share(diff: str) -> float | None:
    """Fraction of the commit's changed lines that live in documentation files."""
    doc_lines = total = 0
    for chunk in split_diff(diff):
        path = chunk_path(chunk)
        changed = sum(count_changes(chunk))
        total += changed
        if path and _is_doc(path):
            doc_lines += changed
    return doc_lines / total if total else None


def doc_guard_note(files: list[str], diff: str = "") -> str:
    """The caution about documentation prose for this commit, or "" if none applies.

    Three cases, not two. All documentation is the easy one. The dangerous one is
    *mixed*: a 900-line CHANGELOG entry plus a one-line typo fix used to switch the
    guard off entirely and come back as "feat: implement <the feature the changelog
    describes>" — the exact failure this tool exists to prevent.
    """
    docs = [f for f in files if _is_doc(f)]
    if not docs:
        return ""
    if len(docs) == len(files):
        return _DOC_ONLY_NOTE
    share = doc_line_share(diff)
    share_text = ""
    if share is not None and share >= 0.5:
        # Capped at 99: code is present by definition here, so rounding 900/901 up
        # to "100% of the changed lines" would contradict the sentence before it.
        share_text = (
            f" Documentation is {min(99, round(share * 100))}% of the changed lines, "
            "so the commit is mostly a documentation edit."
        )
    return _MIXED_DOCS_NOTE.format(files=", ".join(docs), share=share_text)


# --- from commitclerk/secrets.py --------------------------------------

# Only the shapes that identify a vendor's credential on sight: each is anchored
# on a prefix nothing else uses, so these run on every file whatever its class.
# A false positive here takes a deliberately odd fixture, which is why the
# entropy heuristic below is the one that gets held back.
PREFIX_PATTERNS = (
    ("openai-api-key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{16,}")),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}")),
    ("github-pat", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("aws-access-key-id", re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}")),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("google-api-key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "json-web-token",
        re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    ),
)

# Where a lockfile's integrity hashes and a minified bundle's identifiers live:
# nearly the whole false-positive population of the entropy heuristic, and files
# whose contents this tool has already decided never to narrate. The prefix
# patterns above still run there -- an `AKIA...` in a vendored file is a leak.
UNSCANNED_FOR_ENTROPY = ("generated", "vendor", "binary")

# A run of credential-shaped characters long enough to be worth measuring. 24 is
# below every token the patterns above describe and above the identifiers a diff
# is otherwise full of. `=` is base64 padding and so may only trail: allowed
# anywhere it glues `OPENAI_API_KEY=` onto the value and dilutes the very
# entropy this is here to measure.
ENTROPY_TOKEN = re.compile(r"[A-Za-z0-9+/_-]{24,}={0,2}")
MIN_ENTROPY = 4.0

MASK = "[redacted]"
# How many findings the refusal lists before summarising the rest. A screen of
# them is not more actionable than the first few and the count.
MAX_REPORTED = 10

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)")


class Finding(NamedTuple):
    """One suspected secret: where it is and what recognised it, never the text."""

    path: str
    line: int
    detector: str


def shannon_entropy(text: str) -> float:
    """Bits per character -- the usual measure of how little a string repeats."""
    if not text:
        return 0.0
    total = len(text)
    return -sum(
        (count / total) * math.log2(count / total) for count in Counter(text).values()
    )


def looks_random(token: str) -> bool:
    """Whether a long token mixes cases and digits and does not repeat itself.

    The three character classes are what separate a credential from the other
    long tokens a diff is full of: a path has no digits, a `snake_case`
    identifier has no uppercase, an `UPPER_SNAKE` constant has no lowercase, and
    a lowercase hex digest has neither -- nor, at four bits per character
    maximum, the entropy. That last one is a deliberate miss: a hex secret is
    indistinguishable from a git SHA or a checksum, and firing on every digest
    in a diff is the false-positive rate that gets a scanner switched off for
    good, which is a worse outcome than the miss.
    """
    return (
        any(c.isdigit() for c in token)
        and any(c.isupper() for c in token)
        and any(c.islower() for c in token)
        and shannon_entropy(token) >= MIN_ENTROPY
    )


def _sweep(hits: list) -> list:
    """Drop every hit overlapping one already kept, reading left to right."""
    kept: list = []
    reached = 0
    for hit in sorted(hits, key=lambda h: (h[1], -h[2])):
        if hit[1] >= reached:
            kept.append(hit)
            reached = hit[2]
    return kept


def _overlaps(hit: tuple, others: list) -> bool:
    return any(hit[1] < other[2] and other[1] < hit[2] for other in others)


def scan_line(text: str, *, entropy: bool = True) -> list:
    """(detector, start, end) for each match on one line, left to right, no overlaps.

    The heuristic is resolved *after* the named patterns and never displaces
    one, rather than both being swept by position: a JWT is a high-entropy
    string too, and so is `OPENAI_API_KEY=sk-...` read as a single token -- in
    both cases the vendor's name is the more useful thing to be told, and
    position alone would hand the report to whichever span happened to start
    one character earlier.
    """
    named = _sweep(
        [
            (name, match.start(), match.end())
            for name, pattern in PREFIX_PATTERNS
            for match in pattern.finditer(text)
        ]
    )
    if not entropy:
        return named
    guessed = [
        ("high-entropy-string", match.start(), match.end())
        for match in ENTROPY_TOKEN.finditer(text)
        if looks_random(match.group())
    ]
    return _sweep(named + [hit for hit in guessed if not _overlaps(hit, named)])


def added_lines(diff: str):
    """(path, line number, text) for every added line of `diff`, in diff order.

    The number is the line's own number in the file's new side, counted off the
    hunk headers: "line 512 of that file" is something a person can open, and
    "line 40 of the diff" is not. Added lines only -- a secret being *removed*
    is already in the history, and this tool is not where that gets relitigated.
    """
    for chunk in split_diff(diff):
        path = chunk_path(chunk) or "(unknown file)"
        lineno = 0
        for raw in chunk.splitlines():
            hunk = _HUNK.match(raw)
            if hunk:
                lineno = int(hunk.group(1))
            elif raw.startswith(("+++", "---")):
                continue
            elif raw.startswith("+"):
                yield path, lineno, raw[1:]
                lineno += 1
            elif not raw.startswith("-"):
                lineno += 1


def _entropy_allowed(classes: dict, path: str) -> bool:
    return classes.get(path) not in UNSCANNED_FOR_ENTROPY


def scan_diff(diff: str, classes: dict | None = None) -> list:
    """Every suspected secret on an added line, in diff order.

    Asked of the *raw* staged diff, before demotion and before the budget: every
    later point is downstream of a request, and `--deep` sends each oversized
    file in full in a call of its own.
    """
    classes = classes or {}
    return [
        Finding(path, lineno, name)
        for path, lineno, text in added_lines(diff)
        for name, _start, _end in scan_line(text, entropy=_entropy_allowed(classes, path))
    ]


def _mask(text: str, hits: list) -> str:
    """Replace each hit with MASK, right to left so earlier offsets stay valid."""
    for _name, start, end in reversed(hits):
        text = text[:start] + MASK + text[end:]
    return text


def redact_diff(diff: str, classes: dict | None = None) -> tuple:
    """(diff with every match masked, how many were masked).

    This protects the request, never the repository: the staged content is
    untouched and the commit still contains the secret. Any notice about this
    has to say so, or the flag is a false assurance.
    """
    classes = classes or {}
    masked = 0
    out = []
    for chunk in split_diff(diff):
        entropy = _entropy_allowed(classes, chunk_path(chunk) or "(unknown file)")
        lines = []
        for raw in chunk.splitlines(keepends=True):
            if raw.startswith("+") and not raw.startswith("+++"):
                text = raw[1:]
                body = text.rstrip("\r\n")
                hits = scan_line(body, entropy=entropy)
                if hits:
                    masked += len(hits)
                    raw = "+" + _mask(body, hits) + text[len(body):]
            lines.append(raw)
        out.append("".join(lines))
    return "".join(out), masked


def refusal_notice(findings: list) -> str:
    """What to print instead of sending, naming where and never what.

    The match itself is never shown. A terminal is somewhere a secret gets
    scrolled past, copied out of and pasted into a bug report, and the location
    is the whole of what the person needs in order to act.
    """
    if not findings:
        return ""
    count = len(findings)
    subject = "1 possible secret" if count == 1 else f"{count} possible secrets"
    lines = [f"Error: the staged diff contains {subject}; nothing was sent."]
    lines += [f"  {f.path}:{f.line} ({f.detector})" for f in findings[:MAX_REPORTED]]
    hidden = count - MAX_REPORTED
    if hidden > 0:
        lines.append(f"  ... and {hidden} more.")
    lines.append(
        "Unstage them, or re-run with --redact to mask them in the request (the "
        "commit still contains them), or --no-scan to send them anyway."
    )
    return "\n".join(lines)


def redaction_notice(masked: int) -> str:
    """What to print when `--redact` masked something, or "" when it masked nothing."""
    if masked <= 0:
        return ""
    one = masked == 1
    subject = "1 possible secret" if one else f"{masked} possible secrets"
    return (
        f"Note: masked {subject} in the request. The commit is unchanged and "
        f"still contains {'it' if one else 'them'}."
    )


# --- from commitclerk/offline.py --------------------------------------

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


# --- from commitclerk/history.py --------------------------------------

# 200 is enough to see a convention and short enough that `git log` stays instant.
HISTORY_DEPTH = 200
# The whole block, header and footer included. Subtracted from the diff budget by
# the caller rather than added on top of it.
MAX_HOUSE_STYLE_CHARS = 600
# Below this a "convention" is an accident.
MIN_COMMITS = 5
# ASCII record and unit separators: neither can occur in a commit message, unlike a
# newline. The record separator *leads* each record because `git log --name-only`
# prints the touched paths after the format string, and they belong to that commit.
RECORD_SEP = "\x1e"
FIELD_SEP = "\x1f"

# Worked examples: how many, how much of each body, and how little overlap is still
# worth calling an example.
MAX_EXAMPLES = 3
MAX_EXAMPLE_BODY_CHARS = 400
MAX_EXAMPLES_CHARS = 1_400
MIN_PATH_OVERLAP = 0.1

_CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[A-Za-z][A-Za-z0-9]{1,11})(?:\((?P<scope>[^()\n]{1,40})\))?!?:\s+\S"
)
_BULLET_RE = re.compile(r"^\s*([-*•])\s+\S")
_TRAILER_RE = re.compile(r"^(?P<key>[A-Za-z][A-Za-z-]{1,30}):\s+\S")
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# Distinctive markers, not full stopword lists. Portuguese and Spanish share so
# much that a naive frequency count reliably picks the neighbour, so each set is
# weighted towards words that are rare or absent in the other four. Accents are
# folded before matching, which is why the entries are unaccented.
_LANGUAGE_WORDS = {
    "English": {
        "the", "and", "with", "for", "from", "when", "that", "this", "into",
        "add", "adds", "fix", "fixes", "remove", "update", "make", "use",
        "only", "also", "new", "support", "instead", "keep",
    },
    # "corrige", "para" and "ajusta" are spelled identically in Portuguese,
    # Spanish and (the first) French, so they appear in none of the three: a
    # marker shared by the languages it has to separate only produces a tie.
    "Portuguese": {
        "nao", "com", "dos", "das", "uma", "ao", "aos", "pelo", "pela",
        "adiciona", "atualiza", "melhora", "remocao", "arquivo",
        "mensagem", "versao", "tambem", "quando",
    },
    "Spanish": {
        "anade", "anadir", "elimina", "mejora", "los", "las", "del", "hacia",
        "archivo", "mensaje", "version", "tambien", "cuando", "actualiza", "una",
    },
    "French": {
        "ajoute", "supprime", "les", "des", "une", "pour", "avec",
        "dans", "fichier", "sur", "lors", "vers", "aussi", "nouvelle",
    },
    "German": {
        "und", "der", "die", "das", "fur", "mit", "von", "nicht", "ein", "eine",
        "auf", "hinzu", "behebt", "entfernt", "aktualisiert", "datei", "wenn",
    },
}


def split_records(text: str) -> list[str]:
    """Split the raw `git log` output into one record per commit."""
    return [record.strip("\n") for record in text.split(RECORD_SEP) if record.strip()]


def parse_commit(record: str) -> tuple[str, str]:
    """One record's subject line and its body, without the touched-path list."""
    message = record.split(FIELD_SEP, 1)[0]
    subject, _, body = message.partition("\n")
    return subject.strip(), body.strip("\n")


def commit_paths(record: str) -> list[str]:
    """The files one record's commit touched, or [] when it carries no path list."""
    parts = record.split(FIELD_SEP, 1)
    if len(parts) < 2:
        return []
    return [line.strip() for line in parts[1].splitlines() if line.strip()]


def subject_type_scope(subject: str) -> tuple[str | None, str | None]:
    """The Conventional Commits type and scope of a subject, if it has them."""
    match = _CONVENTIONAL_RE.match(subject)
    if not match:
        return None, None
    scope = (match.group("scope") or "").strip().lower()
    return match.group("type").lower(), scope or None


def strip_prefix(subject: str) -> str:
    """A subject without its `type(scope):` prefix, for language scoring.

    `fix:` is English in every repository on earth, so leaving the prefix in makes
    every history look English.
    """
    match = _CONVENTIONAL_RE.match(subject)
    return subject[match.end() - 1:].strip() if match else subject


def body_shape(body: str) -> str:
    """Whether one commit body is "bullets", "prose" or "none"."""
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines:
        return "none"
    if any(_BULLET_RE.match(line) for line in lines):
        return "bullets"
    return "prose"


def bullet_marker(body: str) -> str | None:
    """The character this body bullets with, or None if it is not bulleted."""
    for line in body.splitlines():
        match = _BULLET_RE.match(line)
        if match:
            return match.group(1)
    return None


def trailer_keys(body: str) -> set:
    """Trailer keys in a body's final paragraph: {"Refs"}, {"Co-authored-by"}, ...

    Only the last paragraph, and only when *every* line in it is a trailer —
    otherwise prose like "Note: this is temporary" is counted as a convention the
    repo does not have.
    """
    paragraphs = [p for p in body.split("\n\n") if p.strip()]
    if not paragraphs:
        return set()
    keys = set()
    for line in paragraphs[-1].splitlines():
        if not line.strip():
            continue
        match = _TRAILER_RE.match(line)
        if not match:
            return set()
        keys.add(match.group("key"))
    return keys


def _fold(text: str) -> str:
    """Lowercased and stripped of accents, so "não" and "nao" are one word."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _clip(text: str, limit: int) -> str:
    """`text` shortened to `limit`, cut at a line boundary when one is available."""
    if len(text) <= limit:
        return text
    kept: list[str] = []
    used = 0
    for line in text.splitlines():
        if used + len(line) + 1 > limit:
            break
        kept.append(line)
        used += len(line) + 1
    return "\n".join(kept) + "\n[...]" if kept else text[:limit] + "[...]"


def _ranked(values) -> list:
    """(value, count) pairs, most frequent first, ties broken alphabetically."""
    counts: dict = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))


def dominant_language(subjects: list[str]) -> str | None:
    """The language these subjects are written in, or None when it is not clear.

    Deliberately abstains rather than guesses: telling the model a Portuguese repo
    writes Spanish is worse than saying nothing about language at all. The winner
    must both double the runner-up and be supported by a quarter of the subjects.
    """
    if not subjects:
        return None
    scores = {name: 0 for name in _LANGUAGE_WORDS}
    for subject in subjects:
        words = set(_WORD_RE.findall(_fold(strip_prefix(subject))))
        for name, markers in _LANGUAGE_WORDS.items():
            if words & markers:
                scores[name] += 1
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    (best, top), (_, runner_up) = ranked[0], ranked[1]
    if top < max(2, len(subjects) * 0.25) or top < runner_up * 2:
        return None
    return best


def strip_trailers(body: str) -> str:
    """A body without its trailing trailer block.

    An example is borrowed for its *tone*, and a copied `Co-authored-by:` would
    credit a person who had nothing to do with the commit being written.
    """
    if not trailer_keys(body):
        return body
    paragraphs = [p for p in body.split("\n\n") if p.strip()]
    return "\n\n".join(paragraphs[:-1])


def path_tokens(paths: list[str]) -> set:
    """Every path plus every directory above it — the vocabulary commits are compared on.

    Including the ancestors is what makes the score mean "same subsystem" rather
    than "same file": two commits under `src/api/` overlap even with no file in
    common, while two that touch the identical file overlap far more strongly.
    """
    tokens = set()
    for path in paths:
        current = path.replace("\\", "/").strip().strip("/")
        while current:
            tokens.add(current)
            current = current.rsplit("/", 1)[0] if "/" in current else ""
    return tokens


def similar_commits(
    records: list[str],
    paths: list[str],
    *,
    limit: int = MAX_EXAMPLES,
    min_overlap: float = MIN_PATH_OVERLAP,
) -> list[str]:
    """Past commits whose touched paths overlap `paths` most, best first.

    Jaccard, so a commit that touched four hundred files does not win every
    comparison by sheer size. Below `min_overlap` an "example" is just a recent
    commit about unrelated code, which teaches the model nothing and costs budget.
    """
    target = path_tokens(paths)
    if not target:
        return []
    scored = []
    for index, record in enumerate(records):
        tokens = path_tokens(commit_paths(record))
        if not tokens:
            continue
        overlap = len(target & tokens) / len(target | tokens)
        if overlap >= min_overlap:
            # `index` breaks ties towards the more recent commit: git log is newest
            # first, and the newer of two equally relevant examples is the better one.
            scored.append((-overlap, index, record))
    scored.sort()
    return [record for _, _, record in scored[:limit]]


# Emphatic on purpose. Past commit messages are the one thing in this prompt that
# looks exactly like the answer, and the tool's founding failure is describing work
# from *earlier* commits as work done in this one.
_EXAMPLES_HEADER = (
    "How this repo writes commit messages about these same files. Each block below "
    "is a DIFFERENT, EARLIER commit, shown only so you can match its voice, "
    "structure and level of detail. Nothing in them is part of the commit you are "
    "describing now, and no claim they make may be restated as work done here."
)


def worked_examples(
    records: list[str],
    paths: list[str],
    *,
    limit: int = MAX_EXAMPLES,
    body_limit: int = MAX_EXAMPLE_BODY_CHARS,
    total_limit: int = MAX_EXAMPLES_CHARS,
) -> str:
    """Few-shot examples drawn from this repo's own history, or "" when there are none.

    The classic few-shot quality jump, except the examples are perfectly
    on-distribution: the same team wrote them about the same code. It improves as
    the repository ages and costs no extra API call.
    """
    blocks = []
    used = len(_EXAMPLES_HEADER)
    for record in similar_commits(records, paths, limit=limit):
        subject, body = parse_commit(record)
        if not subject:
            continue
        block = "--- earlier commit, for style only ---\n" + subject
        body = strip_trailers(body).strip()
        if body:
            block += "\n" + _clip(body, body_limit)
        if used + len(block) + 2 > total_limit:
            break
        blocks.append(block)
        used += len(block) + 2
    return "\n\n".join([_EXAMPLES_HEADER] + blocks) if blocks else ""


def known_scopes(records: list[str]) -> list[str]:
    """The scopes this repo's recent commits actually use, most frequent first.

    The same measurement the house-style block reports, handed to scope inference
    (`files.scope_note`) so observation and inference cannot contradict each other.
    An empty list is a finding, not a failure: this repo does not use scopes.
    """
    scopes = [
        scope
        for scope in (subject_type_scope(parse_commit(r)[0])[1] for r in records)
        if scope
    ]
    return [name for name, _ in _ranked(scopes)]


def known_types(records: list[str]) -> list[str]:
    """The Conventional Commits types this repo's commits use, most frequent first.

    The companion of `known_scopes`, off the same measurement the house-style
    block reports. An empty list is a finding, not a failure: the history was
    read and this repo does not prefix its subjects, which is an instruction not
    to start -- see `offline.offline_type`, the only caller that can act on it.
    """
    types = [
        kind
        for kind in (subject_type_scope(parse_commit(r)[0])[0] for r in records)
        if kind
    ]
    return [name for name, _ in _ranked(types)]


def _facts(commits: list) -> list[str]:
    """The house-style observations, most useful first."""
    subjects = [subject for subject, _ in commits]
    bodies = [body for _, body in commits]
    parsed = [subject_type_scope(s) for s in subjects]
    types = [t for t, _ in parsed if t]
    scopes = [s for _, s in parsed if s]

    lines = []
    share = round(100 * len(types) / len(subjects))
    if types:
        lines.append(
            f"- {share}% of subjects use a Conventional Commits prefix; types in use: "
            + ", ".join(f"{name} {n}" for name, n in _ranked(types)[:6])
            + "."
        )
    else:
        lines.append(
            "- Subjects do NOT use Conventional Commits prefixes; do not add one."
        )
    if scopes:
        lines.append(
            "- Scopes in use: "
            + ", ".join(f"{name} {n}" for name, n in _ranked(scopes)[:8])
            + "."
        )

    shapes = _ranked(body_shape(b) for b in bodies)
    dominant_shape, count = shapes[0]
    body_line = f"- Bodies are usually {dominant_shape} ({round(100 * count / len(bodies))}%)"
    if dominant_shape == "bullets":
        markers = _ranked(m for m in (bullet_marker(b) for b in bodies) if m)
        body_line += f", bulleted with '{markers[0][0]}'"
    lines.append(body_line + ".")

    language = dominant_language(subjects)
    if language:
        lines.append(f"- Subjects are written in {language}; write this message in it too.")

    lengths = sorted(len(s) for s in subjects)
    lines.append(f"- Median subject length: {lengths[len(lengths) // 2]} characters.")

    trailers = _ranked(k for body in bodies for k in trailer_keys(body))
    if trailers:
        lines.append(
            "- Trailers in use: " + ", ".join(name for name, _ in trailers[:4]) + "."
        )
    return lines


def house_style(records: list[str], *, limit: int = MAX_HOUSE_STYLE_CHARS) -> str:
    """A compact description of how this repo writes commits, or "" if unknowable."""
    commits = [parse_commit(r) for r in records]
    commits = [(subject, body) for subject, body in commits if subject]
    if len(commits) < MIN_COMMITS:
        return ""

    header = f"House style, measured from this repo's last {len(commits)} commits:"
    footer = (
        "Follow it over generic defaults; prefer a type and scope that already "
        "appear above, and introduce a new one only when none fits."
    )
    budget = limit - len(header) - len(footer) - 2
    kept: list[str] = []
    for line in _facts(commits):
        if len(line) + 1 > budget:
            break
        kept.append(line)
        budget -= len(line) + 1
    if not kept:
        return ""
    return "\n".join([header] + kept + [footer])


# --- from commitclerk/gitio.py ----------------------------------------

# thousand-file commit still needs a ceiling.
MAX_SUMMARY_CHARS = 2_000

def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def get_repo_root() -> str | None:
    """The repository's top level, or None when we are not inside one.

    This is where `.clerk.json` is looked for, so that the tool behaves the same
    from the root and from three directories down.
    """
    try:
        result = run(["git", "rev-parse", "--show-toplevel"], check=False)
    except (OSError, UnicodeDecodeError):
        return None
    root = result.stdout.strip()
    return root or None


def get_branch_name() -> str | None:
    """The current branch, or None outside a repository.

    A detached HEAD answers with the literal `HEAD`, which is passed through
    rather than special-cased: it carries no issue key, so it finds none.
    """
    try:
        result = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], check=False)
    except (OSError, UnicodeDecodeError):
        return None
    return result.stdout.strip() or None


def get_staged_diff() -> str:
    return run(["git", "diff", "--staged"], check=False).stdout


def get_unstaged_files() -> list[str]:
    """Files with changes in the working tree that are not staged."""
    result = run(["git", "diff", "--name-only"], check=False)
    return [line for line in result.stdout.splitlines() if line.strip()]


def partially_staged(staged: list[str], unstaged: list[str]) -> list[str]:
    """Staged files that also have further, unstaged edits on disk."""
    pending = set(unstaged)
    return [f for f in staged if f in pending]


def unstaged_warning(mixed: list[str], limit: int = 5) -> str:
    """One line naming partially staged files, or "" when there are none.

    `git add -p` makes this routine, and the consequence is easy to miss: the
    message describes the staged version of the code, which is not the version on
    disk. Inform, never block — the staged diff is what is being committed, so the
    message is correct; it is the user's mental model that may be wrong.
    """
    if not mixed:
        return ""
    shown = ", ".join(mixed[:limit])
    if len(mixed) > limit:
        shown += f", and {len(mixed) - limit} more"
    noun = "file has" if len(mixed) == 1 else "files have"
    return (
        f"Note: {len(mixed)} staged {noun} unstaged changes too, so the message "
        f"describes the staged version, not what is on disk: {shown}"
    )


def get_staged_summary() -> str:
    """Structural facts about the staged change, which the diff body omits.

    `--stat` carries insertion/deletion counts and the *sizes* of binary files;
    `--summary` names creations, deletions, renames and mode changes. `-M` is
    passed explicitly rather than trusting `diff.renames`, so a repo that turned
    rename detection off still gets "rename a => b" instead of a delete plus an
    add that reads like a rewrite.
    """
    result = run(
        ["git", "diff", "--staged", "--find-renames", "--stat=200,180", "--summary"],
        check=False,
    )
    # strip("\n") only: git indents the stat table by one space, and keeping that
    # indentation keeps the columns aligned for the model.
    return truncate(result.stdout.strip("\n"), MAX_SUMMARY_CHARS)


def get_recent_commits(depth: int = HISTORY_DEPTH) -> list[str]:
    """The last `depth` non-merge commits as `subject\\n\\nbody<FIELD_SEP>paths` records.

    Merges are excluded because their subjects are generated by git, not written
    by the team, and a busy repo's history is otherwise half "Merge pull request".
    One call carries both halves of the history context: the message, which the
    house-style fingerprint measures, and the touched paths, which decide which
    past commits are worth showing as worked examples.

    Any failure returns no records: history context is an enhancement, and it must
    never be the reason a commit cannot be written. Old commits in a long-lived
    repo are a real source of undecodable bytes, so that case is caught here rather
    than crashing three frames up.
    """
    try:
        result = run(
            [
                "git", "log", f"-n{depth}", "--no-merges", "--name-only",
                f"--format={RECORD_SEP}%s%n%b{FIELD_SEP}",
            ],
            check=False,
        )
    except (OSError, UnicodeDecodeError):
        return []
    return split_records(result.stdout)


def get_staged_files() -> list[str]:
    result = run(["git", "diff", "--staged", "--name-only"], check=False)
    return [line for line in result.stdout.splitlines() if line.strip()]


# --- from commitclerk/trailers.py -------------------------------------

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


# --- from commitclerk/prompt.py ---------------------------------------

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

def _file_line(path: str, classes: dict, excluded) -> str:
    """`- path (class, excluded)` -- the class, then whether the body is withheld.

    Two annotations and not one: the class says what kind of file it is, which
    is what the type prefix is picked from, and exclusion says only what the
    model may see. An excluded lockfile and excluded source must not read alike.
    """
    marks = ([classes[path]] if path in classes else []) + (
        ["excluded"] if path in excluded else []
    )
    return f"- {path} ({', '.join(marks)})" if marks else f"- {path}"


def build_user_prompt(
    diff: str,
    files: list[str],
    *,
    title: str | None = None,
    guard: str = "",
    summary: str = "",
    classes: dict | None = None,
    house_style: str = "",
    examples: str = "",
    scope: str = "",
    context: str = "",
    deep: str = "",
    excluded=(),
) -> str:
    classes = classes or {}
    parts = []
    if house_style:
        # First: it is the frame everything below is read through, and unlike the
        # guard it is not competing with the diff for the model's attention — it
        # describes the shape of the answer, not what the answer is about.
        parts += [house_style, ""]
    if examples:
        # Beside the fingerprint, and well before the diff. Both answer "how should
        # this be written"; everything from the file list down answers "about what".
        parts += [examples, ""]
    parts += ["Files changed:"] + [_file_line(f, classes, excluded) for f in files]
    if classes:
        parts += [f"Class mix: {class_mix(classes)}"]
    if scope:
        # Beside the file list it annotates, and before the diff: it is a fact
        # about *which* code changed, which the diff body cannot state.
        parts += [scope]
    if summary:
        # Before the diff, and outside its budget: when a large diff is trimmed
        # this is the part that still describes the whole change.
        parts += ["", "Change summary (git --stat --summary):", summary]
    if context:
        # After the facts about the change, before the diff: it explains what the
        # diff is for, so it has to be read as a frame around the diff rather
        # than as one more thing the diff mentions.
        parts += ["", context]
    if title is not None:
        parts += ["", f"Commit title (already chosen by the author, do not repeat it): {title}"]
    if deep:
        # Immediately above the diff, because it is the key to a notation that
        # only appears inside it: read anywhere else it explains nothing.
        parts += ["", deep]
    parts += ["", "Unified diff:", diff]
    if guard:
        # Last, on purpose. Measured against gpt-4o-mini: with the guard placed
        # before the diff, 48 lines of changelog prose came after it and won — the
        # model still wrote "feat: implement real-time collaboration" for a commit
        # whose only code change was a docstring. Read after the diff, it obeys.
        parts += ["", guard]
    return "\n".join(parts)


# --- from commitclerk/providers.py ------------------------------------

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"
DEFAULT_OLLAMA_MODEL = "qwen2.5-coder"
DEFAULT_PROVIDER = "openai"
REQUEST_TIMEOUT = 60

# Transient failures: rate limits, gateway hiccups, and Anthropic's 529 overload.
RETRY_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504, 529})
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 1.0
RETRY_MAX_DELAY = 30.0

# Sampling knobs a model may reject and the request does not need: if a 400 names
# one of these, drop it and ask again. Required fields are never dropped.
DROPPABLE_PARAMS = frozenset({
    "temperature", "top_p", "top_k", "frequency_penalty", "presence_penalty",
})
# The request itself. Never repaired — and `model` in particular is a trap, because
# almost every 400 says "with this model", which would match it by accident.
PROTECTED_PARAMS = frozenset({"model", "messages", "system", "prompt", "input", "stream"})
# "Use 'max_completion_tokens' instead" — a rename the provider spelled out for us.
_INSTEAD_RE = re.compile(r"use\s+['\"]?([a-z]\w*)['\"]?\s+instead", re.IGNORECASE)

# Anthropic requires max_tokens and pins the wire format with a version header.
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MAX_TOKENS = 8192

def _openai_payload(model: str, system: str, user: str) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }


def _openai_extract(data: dict) -> str:
    return data["choices"][0]["message"]["content"]


def _anthropic_payload(model: str, system: str, user: str) -> dict:
    # Four things differ from the Chat Completions shape: the system prompt is a
    # top-level field rather than a message, max_tokens is required, the response
    # is a list of content blocks, and the auth header is x-api-key. No
    # temperature: current reasoning models reject it outright (HTTP 400), and
    # the rules in the prompt already constrain the output far more than a
    # sampling knob would.
    return {
        "model": model,
        "max_tokens": ANTHROPIC_MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }


def _anthropic_extract(data: dict) -> str:
    """First text block — not `content[0]`, which may be a thinking block."""
    for block in data.get("content") or []:
        if block.get("type") == "text":
            return block.get("text", "")
    return ""


# A provider is four small slots — url, headers, payload, extract — in a table,
# not a class hierarchy: this file is meant to be read in one sitting, and those
# four slots are exactly what differs between vendors.
PROVIDERS: dict[str, dict] = {
    "openai": {
        "label": "OpenAI",
        "default_base": "https://api.openai.com/v1",
        "path": "/chat/completions",
        "base_env": "OPENAI_BASE_URL",
        "key_env": "OPENAI_API_KEY",
        "key_required": True,
        "model_env": "OPENAI_MODEL",
        "default_model": DEFAULT_MODEL,
        "headers": lambda key: {"Authorization": f"Bearer {key}"},
        "payload": _openai_payload,
        "extract": _openai_extract,
    },
    "anthropic": {
        "label": "Anthropic",
        "default_base": "https://api.anthropic.com/v1",
        "path": "/messages",
        "base_env": "ANTHROPIC_BASE_URL",
        "key_env": "ANTHROPIC_API_KEY",
        "key_required": True,
        "model_env": "ANTHROPIC_MODEL",
        "default_model": DEFAULT_ANTHROPIC_MODEL,
        "headers": lambda key: {
            "x-api-key": key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
        "payload": _anthropic_payload,
        "extract": _anthropic_extract,
    },
    # A local server speaking the OpenAI wire format: same two adapter functions,
    # a localhost base URL, and no key at all — this is the "the diff never leaves
    # this machine" path, so it has to work with nothing configured.
    "ollama": {
        "label": "Ollama",
        "default_base": "http://localhost:11434/v1",
        "path": "/chat/completions",
        "base_env": "OLLAMA_BASE_URL",
        "key_required": False,
        "model_env": "OLLAMA_MODEL",
        "default_model": DEFAULT_OLLAMA_MODEL,
        "headers": lambda key: {},
        "payload": _openai_payload,
        "extract": _openai_extract,
    },
}


def resolve_provider(name: str) -> dict | None:
    """The adapter for `name`, or None when no such provider is registered.

    argparse validates `--provider`, but $CLERK_PROVIDER arrives as a default
    and defaults skip `choices` — so this lookup has to be able to fail.
    """
    return PROVIDERS.get(name)


def resolve_model(
    spec: dict,
    cli_model: str | None = None,
    project: str | None = None,
    user: str | None = None,
) -> str:
    """Model to call, through the one ladder in `config.py`.

    The provider's own env var is this setting's environment layer: `OPENAI_MODEL`
    for openai, `ANTHROPIC_MODEL` for anthropic.
    """
    return layered(
        cli_model or None,
        env_value(spec.get("model_env")),
        project,
        user,
        spec["default_model"],
    )


def api_key_for(spec: dict) -> str | None:
    env = spec.get("key_env")
    return os.environ.get(env) if env else None


def missing_key_env(spec: dict) -> str | None:
    """Env var the user must set, when this provider needs a key and has none.

    A provider that needs no key at all (a local model) must not be blocked by
    a key check, so the check belongs to the provider, not to main().
    """
    env = spec.get("key_env")
    if env and spec.get("key_required", True) and not os.environ.get(env):
        return env
    return None


def resolve_base(
    spec: dict,
    cli_base: str | None = None,
    project: str | None = None,
    user: str | None = None,
) -> str:
    """Base URL to call, through the one ladder in `config.py`.

    Most vendors clone the OpenAI wire format, so pointing this at Ollama,
    LM Studio, vLLM, OpenRouter, Groq, Together or Azure needs no new adapter.
    """
    return layered(
        cli_base or None,
        env_value(spec.get("base_env")),
        project,
        user,
        spec["default_base"],
    )


def base_url_error(base: str) -> str | None:
    """Complaint about `base`, or None when it is usable.

    A base URL missing its scheme (`localhost:11434/v1`) otherwise dies deep in
    urllib with "unknown url type", which reads like a bug in the tool.
    """
    scheme = base.split("://", 1)[0].lower() if "://" in base else ""
    if scheme not in ("http", "https"):
        return f"base URL must start with http:// or https:// (got '{base}')"
    if not base.split("://", 1)[1].strip("/"):
        return f"base URL has no host (got '{base}')"
    return None


def provider_url(spec: dict, base: str | None = None) -> str:
    return (base or spec["default_base"]).rstrip("/") + spec["path"]


def retry_after_seconds(value: str | None) -> float | None:
    """The `Retry-After` header as seconds, or None if it isn't a plain number.

    The header may also carry an HTTP date; rather than parse dates, fall back to
    the backoff schedule, which is never longer than RETRY_MAX_DELAY anyway.
    """
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def retry_delay(attempt: int, retry_after: str | None = None) -> float:
    """Seconds to wait after a failed `attempt` (1-based).

    Exponential (1s, 2s, 4s, ...) with jitter, so a rate-limited team does not
    retry in lockstep. A server-supplied `Retry-After` wins — it knows better
    than we do — but is still capped, so a hostile or confused header cannot
    park a commit for an hour.
    """
    supplied = retry_after_seconds(retry_after)
    if supplied is not None:
        return min(supplied, RETRY_MAX_DELAY)
    backoff = min(RETRY_BASE_DELAY * (2 ** (attempt - 1)), RETRY_MAX_DELAY)
    # Spread, not secrecy: `random` is the right tool for jitter.
    return backoff * (0.5 + random.random() / 2)


def _is_retryable_url_error(exc: urllib.error.URLError) -> bool:
    # A refused connection is a wrong address or a server that is not running —
    # common with --provider ollama, and never worth three attempts.
    return not isinstance(getattr(exc, "reason", None), ConnectionRefusedError)


def _names_parameter(body: str, key: str) -> bool:
    """Whether `body` mentions `key` as a whole word, not as part of another name."""
    return re.search(r"(?<!\w)" + re.escape(key) + r"(?!\w)", body, re.IGNORECASE) is not None


def suggested_replacement(body: str, key: str) -> str | None:
    """A parameter name the error body tells us to use instead of `key`.

    Providers say things like "Use 'max_completion_tokens' instead", which is
    enough to fix the request without a per-model capability table.
    """
    match = _INSTEAD_RE.search(body)
    if not match:
        return None
    name = match.group(1)
    return name if name != key else None


def repair_payload(payload: dict, body: str) -> tuple[dict, str] | None:
    """A payload with the parameter the server rejected renamed or dropped.

    Returns `(payload, what_changed)`, or None when the 400 is not about a
    parameter we can safely change — in which case the caller must not retry.
    Reasoning models reject `temperature` outright and rename `max_tokens`; a
    capability matrix per model would rot within a quarter, so heal instead.
    """
    for key in payload:
        if key in PROTECTED_PARAMS or not _names_parameter(body, key):
            continue
        replacement = suggested_replacement(body, key)
        if replacement:
            repaired = dict(payload)
            repaired[replacement] = repaired.pop(key)
            return repaired, f"renamed {key} to {replacement}"
        if key in DROPPABLE_PARAMS:
            repaired = dict(payload)
            del repaired[key]
            return repaired, f"dropped {key}"
        # Named, but required (model, messages, max_tokens...): dropping it would
        # only trade this error for a worse one.
        return None
    return None


def _post_once(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_failure(
    exc: urllib.error.HTTPError, body: str, *, label: str, attempt: int, budget: int
) -> tuple[float, str]:
    """How long to wait before retrying `exc` — or SystemExit if it is fatal."""
    if exc.code not in RETRY_STATUSES or budget <= 0:
        raise SystemExit(f"{label} API error {exc.code}: {body}")
    header = exc.headers.get("Retry-After") if exc.headers else None
    return retry_delay(attempt, header), f"{label} API error {exc.code}"


def _url_failure(
    exc: urllib.error.URLError, *, label: str, attempt: int, budget: int
) -> tuple[float, str]:
    if not _is_retryable_url_error(exc) or budget <= 0:
        raise SystemExit(f"{label} API request failed: {exc}")
    return retry_delay(attempt), f"{label} API request failed: {exc}"


def post_json(
    url: str,
    payload: dict,
    headers: dict,
    *,
    label: str,
    timeout: int = REQUEST_TIMEOUT,
    attempts: int = RETRY_ATTEMPTS,
) -> dict:
    """POST `payload` as JSON and decode the reply, healing what can be healed.

    Two kinds of failure, two different answers. Rate limits and 5xx blips are
    transient, so they are retried with backoff — on a free tier a single 429 used
    to throw away the whole commit. A 400 about a parameter this tool chose is
    permanent, so backing off would not help: the parameter is repaired and the
    request is sent again, once, without spending the transient budget.
    """
    retries = 0
    repaired = False
    while True:
        try:
            return _post_once(url, payload, headers, timeout)
        except urllib.error.HTTPError as exc:  # a subclass of URLError: catch first
            body = exc.read().decode("utf-8", errors="ignore")
            fix = repair_payload(payload, body) if exc.code == 400 and not repaired else None
            if fix:
                payload, changed = fix
                repaired = True
                print(
                    f"{label} rejected a request parameter; {changed} and retrying",
                    file=sys.stderr,
                )
                continue
            delay, reason = _http_failure(
                exc, body, label=label, attempt=retries + 1, budget=attempts - 1 - retries
            )
        except urllib.error.URLError as exc:
            delay, reason = _url_failure(
                exc, label=label, attempt=retries + 1, budget=attempts - 1 - retries
            )

        retries += 1
        # ASCII only: this goes to a terminal whose encoding we do not control.
        print(
            f"{reason} - retrying in {delay:.1f}s (retry {retries} of {attempts - 1})",
            file=sys.stderr,
        )
        time.sleep(delay)


def complete(
    spec: dict,
    api_key: str | None,
    model: str,
    system: str,
    user: str,
    *,
    base: str | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> str:
    """One request: build the payload, post it, return the text.

    Split out from `call_model` because `--deep` makes a second kind of call --
    a per-file summary — and a second copy of the payload/headers/extract dance
    is a second place for a provider quirk to be fixed only once.
    """
    payload = spec["payload"](model, system, user)
    headers = {"Content-Type": "application/json"}
    headers.update(spec["headers"](api_key))
    data = post_json(
        provider_url(spec, base),
        payload,
        headers,
        label=spec["label"],
        timeout=timeout,
    )
    return spec["extract"](data).strip()


def call_model(
    spec: dict,
    api_key: str | None,
    model: str,
    diff: str,
    files: list[str],
    *,
    context: dict | None = None,
    base: str | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> str:
    # One bag rather than one parameter per prompt section: every context source the
    # tool grows (guard, summary, classes, house style, examples, scope, ...) would
    # otherwise widen this signature and every call site along with it. The keys are
    # `build_user_prompt`'s keyword arguments, which is the only contract there is.
    context = context or {}
    label = spec["label"]
    text = complete(
        spec,
        api_key,
        model,
        _system_prompt(body_only=context.get("title") is not None),
        build_user_prompt(diff, files, **context),
        base=base,
        timeout=timeout,
    )
    if not text:
        # Better to fail than to hand `git commit` an empty message. The usual
        # cause is a reasoning model that spent the whole output budget before
        # writing any prose.
        raise SystemExit(
            f"{label} returned no message text (model: {model}). "
            "Try a smaller diff, or a model that does not reason before answering."
        )
    return text


# --- from commitclerk/cli.py ------------------------------------------

def prog_name(argv0: str) -> str:
    """Name to show in --help, derived from how the tool was actually invoked.

    Installed as `git-clerk`, git runs us for `git clerk`, so printing
    `usage: clerk` there would document a command the user did not type.
    """
    base = os.path.basename(argv0)
    stem = os.path.splitext(base)[0]
    if stem == "git-clerk":
        return "git clerk"
    return stem or "clerk"

def _wants_refs(settings: dict) -> bool | None:
    """Whether one config file asks for the `Refs:` trailer, or None if it is silent.

    Naming a `ticket_pattern` is asking for the trailer, so a file does not have
    to say so twice; `ticket_refs` alone is for a project that wants the built-in
    pattern and nothing to configure. Either can be set to `false` to turn off
    what the file below it in the ladder turned on.
    """
    if "ticket_refs" in settings:
        return settings["ticket_refs"]
    return True if "ticket_pattern" in settings else None


def _wants_examples(house_style_on, cli, project, user) -> bool:
    """Whether worked examples may be sent, given the fingerprint's own answer.

    The narrow half of one refusal: the fingerprint transmits counts and shapes,
    the examples transmit past commit message text verbatim, and a team can want
    the first without the second. Gated on the fingerprint rather than resolved
    beside it, because refusing the whole `git log` has already refused the
    examples -- `"examples": true` under `"house_style": false` would otherwise
    ask for text out of a history nothing read.
    """
    return bool(house_style_on and layered(cli, None, project, user, True))


def finish(message: str, ticket_refs, ticket_pattern: str, *, dry_run: bool) -> int:
    """Trailer, print, commit -- the tail the online and offline paths share.

    The trailer is applied here, after the message exists and never through the
    model: the key is read off the branch, so the one thing that could go wrong
    is a paraphrase, and this way there is none. `--offline` gets it too, the
    branch name being as local as everything else on that path.
    """
    if ticket_refs:
        key = ticket_key(get_branch_name(), ticket_pattern)
        if key:
            message = add_trailer(message, TICKET_TRAILER, key)

    if dry_run:
        print(message)
        return 0

    print("--- commit message ---")
    print(message)
    print("----------------------")

    proc = subprocess.run(
        ["git", "commit", "-F", "-"],
        input=message,
        text=True,
        encoding="utf-8",
    )
    return proc.returncode


def call_target(args, project: dict, user: dict, provider: str) -> tuple:
    """(spec, api_key, model, base, "") for the endpoint to call, or (…, problem).

    Separated from `main` because `--offline` must not run any of it: resolving
    a provider that will never be called turns an unset key into an error on the
    one path that has no use for one.
    """
    spec = resolve_provider(provider)
    if spec is None:
        known = ", ".join(sorted(PROVIDERS))
        return None, None, None, None, (
            f"unknown provider '{provider}'. Known providers: {known}"
        )
    missing = missing_key_env(spec)
    if missing:
        return None, None, None, None, f"{missing} is not set"

    model = resolve_model(spec, args.model, project.get("model"), user.get("model"))
    base = resolve_base(spec, args.base_url, project.get("base_url"), user.get("base_url"))
    problem = base_url_error(base)
    if problem:
        return None, None, None, None, problem
    return spec, api_key_for(spec), model, base, ""


def deepen(
    diff: str,
    budget: int,
    spec: dict,
    api_key: str | None,
    model: str,
    *,
    base: str | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> tuple[str, str]:
    """The map half of `--deep`: (diff with summaries, the note that explains them).

    Asked of the already-demoted diff and against the real budget, so the
    question is the exact one the allocator is about to answer -- which files
    would lose their tail. A commit that already fits names none of them and
    spends nothing, which is what makes the flag safe to leave on in a config
    file. The note comes back empty when no summary was obtained, because a
    notation nothing uses is only budget spent on confusing the model.
    """
    oversized = over_budget_paths(diff, budget)
    if not oversized:
        return diff, ""
    print(
        f"Summarizing {len(oversized)} oversized file(s) "
        f"in {len(oversized)} extra request(s).",
        file=sys.stderr,
    )

    def summarize(path: str, chunk: str) -> str:
        try:
            return complete(
                spec, api_key, model,
                SUMMARY_SYSTEM_PROMPT, summary_user_prompt(path, chunk),
                base=base, timeout=timeout,
            )
        # `post_json` reports a fatal API error by raising this. One file's
        # summary is not worth the commit: say so, and let the file be trimmed
        # exactly as it would have been without the flag.
        except SystemExit as exc:
            print(f"Could not summarize {path} ({exc}).", file=sys.stderr)
            return ""

    diff, summarized = summarize_diff(diff, oversized, summarize)
    return diff, DEEP_NOTE if summarized else ""


def main() -> int:
    parser = argparse.ArgumentParser(
        prog=prog_name(sys.argv[0]),
        description="commitclerk - AI-powered git commit messages.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"commitclerk {__version__}",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the message and exit.")
    parser.add_argument(
        "-m",
        "--message",
        default=None,
        help="Authoritative commit title. When set, it is used verbatim as the title and the AI "
             "writes only the body bullets (most reliable way to avoid a misread of intent).",
    )
    parser.add_argument(
        "--context",
        default=None,
        metavar="NOTE",
        help="One sentence of intent the diff cannot show, e.g. \"this reverts the "
             f"caching experiment\". Standing facts about the repository belong in "
             f"{CONTEXT_FILE} instead, which is read on every run.",
    )
    parser.add_argument(
        "--provider",
        default=None,
        choices=sorted(PROVIDERS),
        help=f"API provider (default: {DEFAULT_PROVIDER}, or $CLERK_PROVIDER, or "
             f"\"provider\" in {PROJECT_CONFIG}).",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Base URL of an OpenAI-compatible endpoint, e.g. http://localhost:11434/v1 "
             "for Ollama (default: the provider's own base URL, or its base-url "
             "environment variable).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model to call (default: the provider's default model, or its model "
             f"environment variable; {DEFAULT_MODEL} / $OPENAI_MODEL for openai).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help=f"Seconds to wait for each API request (default: {REQUEST_TIMEOUT}). A slow "
             f"local model may need more. Transient failures are retried up to "
             f"{RETRY_ATTEMPTS - 1} times.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=None,
        help="Budget for the diff, in characters. Oversized diffs are trimmed per file "
             "so every changed file stays visible to the model, and the contents of "
             "generated or vendored files are replaced by a one-line placeholder.",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        default=None,
        help="Summarize each file too large for the diff budget in its own cheap request, "
             "then write the message from those summaries plus the smaller files' real "
             "diffs. Costs one extra request per oversized file, and nothing at all when "
             "the whole diff already fits.",
    )
    parser.add_argument(
        "--no-house-style",
        action="store_true",
        default=None,
        help=f"Do not read the last {HISTORY_DEPTH} commits. Turns off both the "
             "house-style fingerprint (the types, scopes, body shape and language "
             "this repo uses) and the worked examples drawn from past commits that "
             "touched the same files. Use it to keep past commit message text off "
             "the wire, or when the history is not a style worth copying.",
    )
    parser.add_argument(
        "--no-examples",
        action="store_true",
        default=None,
        help="Do not send past commit message text. Turns off the worked examples "
             "drawn from earlier commits that touched the same files, and keeps the "
             "house-style fingerprint, which reports only counts and shapes. Implied "
             "by --no-house-style.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        default=None,
        help="Write the message locally with no API call, no key and no network. The "
             "type comes from the file classes, the scope from the workspace manifest "
             "and the bullets are grouped by directory. It never guesses feat: or "
             "fix:, which state intent nothing local can see, so it is a draft rather "
             "than a replacement - and it always beats an error when you are offline.",
    )
    parser.add_argument(
        "--redact",
        action="store_true",
        default=None,
        help="Instead of refusing, mask every suspected secret in the request and "
             "carry on. The commit is unchanged and still contains them: this "
             "protects what is sent, not what is committed.",
    )
    parser.add_argument(
        "--no-scan",
        action="store_true",
        default=None,
        help="Do not scan the staged diff for secrets before sending it. Turns off "
             "--redact along with it, there being nothing left to mask.",
    )
    args = parser.parse_args()

    root = get_repo_root()
    try:
        project, user, notices = load_config(root)
        # Parsed on every path, applied only where there is something to
        # withhold: a malformed .clerkignore is a mistake worth reporting even
        # on a run that was never going to transmit anything.
        rules = read_clerkignore(clerkignore_path(root))
    except ConfigError as exc:
        print(f"Error: {exc}.", file=sys.stderr)
        return 2
    for notice in notices:
        print(notice, file=sys.stderr)

    # Every setting below is resolved by the same five-rung ladder, in the order
    # `layered` documents: CLI > environment > project file > user file > default.
    provider = layered(
        args.provider, env_value("CLERK_PROVIDER"),
        project.get("provider"), user.get("provider"), DEFAULT_PROVIDER,
    )
    timeout = layered(
        args.timeout, None, project.get("timeout"), user.get("timeout"), REQUEST_TIMEOUT,
    )
    max_chars = layered(
        args.max_chars, None, project.get("max_chars"), user.get("max_chars"), MAX_DIFF_CHARS,
    )
    # The flag is negative and the setting is positive: passing --no-house-style
    # is the CLI saying `false`, and not passing it says nothing at all.
    house_style_on = layered(
        False if args.no_house_style else None, None,
        project.get("house_style"), user.get("house_style"), True,
    )
    examples_on = _wants_examples(
        house_style_on, False if args.no_examples else None,
        project.get("examples"), user.get("examples"),
    )
    scan_on = layered(
        False if args.no_scan else None, None,
        project.get("scan"), user.get("scan"), True,
    )
    deep_on = layered(
        True if args.deep else None, None, project.get("deep"), user.get("deep"), False,
    )
    ticket_pattern = layered(
        None, None,
        project.get("ticket_pattern"), user.get("ticket_pattern"), DEFAULT_TICKET_PATTERN,
    )
    ticket_refs = layered(
        None, None, _wants_refs(project), _wants_refs(user), False,
    )
    if ticket_refs and compile_ticket_pattern(ticket_pattern) is None:
        print(
            f"Error: 'ticket_pattern' is not a valid regular expression: {ticket_pattern}.",
            file=sys.stderr,
        )
        return 2

    # Not resolved at all under --offline: that path makes no request, so a
    # missing key is not a problem it has, and refusing to write a message over
    # one would reintroduce the outage this flag exists to survive.
    spec = api_key = model = base = None
    if not args.offline:
        spec, api_key, model, base, problem = call_target(args, project, user, provider)
        if problem:
            print(f"Error: {problem}.", file=sys.stderr)
            return 2

    diff = get_staged_diff()
    if not diff.strip():
        print("No staged changes. Run `git add <files>` first.", file=sys.stderr)
        return 1

    files = get_staged_files()
    warning = unstaged_warning(partially_staged(files, get_unstaged_files()))
    if warning:
        print(warning, file=sys.stderr)

    classes = classify_files(files, diff)

    if args.offline:
        # No secret scan on this path: that scan exists to stop a transmission,
        # and there is none. Refusing a commit that sends nothing would make
        # this a pre-commit hook, which is a different tool.
        records = get_recent_commits() if house_style_on else []
        return finish(
            offline_message(
                files, classes, get_staged_summary(),
                title=args.message,
                types=known_types(records) if records else None,
                scopes=known_scopes(records) if len(records) >= MIN_COMMITS else None,
            ),
            ticket_refs, ticket_pattern, dry_run=args.dry_run,
        )

    # Before the scan, not after: content that is never transmitted has nothing
    # to refuse over, which is what makes .clerkignore the escape hatch for a
    # false positive rather than one more thing --no-scan has to switch off.
    hidden = excluded_paths(files, rules)
    if hidden:
        diff = demote_diff(diff, {}, (), excluded=set(hidden))
        print(exclusion_notice(hidden), file=sys.stderr)

    # Before every request, and on the diff as staged rather than as trimmed: a
    # scan placed after demotion or the budget would clear a payload that
    # `--deep`'s own calls have already carried.
    findings = scan_diff(diff, classes) if scan_on else []
    if findings:
        if not args.redact:
            print(refusal_notice(findings), file=sys.stderr)
            return 3
        diff, masked = redact_diff(diff, classes)
        print(redaction_notice(masked), file=sys.stderr)

    summary = get_staged_summary()
    # Both read the raw diff: the guard's proportion must be measured before any
    # trimming, and demotion must happen before budgeting so the space a lockfile
    # was using is handed to the files the commit is actually about.
    guard = doc_guard_note(files, diff)
    records = get_recent_commits() if house_style_on else []
    house = house_style(records)
    # None means no history was read, which is not the same as a history that shows
    # no scopes -- only the second is a reason for scope inference to stay quiet.
    vocabulary = known_scopes(records) if len(records) >= MIN_COMMITS else None
    scope = scope_note(files, vocabulary)
    examples = worked_examples(records, files) if examples_on else ""
    author = context_note(read_context_file(context_path(root)), args.context)

    context = {
        "guard": guard,
        "summary": summary,
        "classes": classes,
        "house_style": house,
        "examples": examples,
        "scope": scope,
        "context": author,
        "excluded": hidden,
    }
    if args.message:
        context["title"] = args.message

    # Subtracted from the diff budget, not added on top of it: the extra context is
    # worth a couple of thousand characters of diff, but it must not silently raise
    # what the user asked to send.
    spent = len(house) + len(scope) + len(examples) + len(author)
    budget = max(0, max_chars - spent)
    diff = demote_diff(diff, classes)

    if deep_on:
        diff, note = deepen(
            diff, budget, spec, api_key, model, base=base, timeout=timeout,
        )
        if note:
            context["deep"] = note
            budget = max(0, budget - len(note))

    diff = budget_diff(diff, budget)

    message = call_model(
        spec, api_key, model, diff, files,
        context=context, base=base, timeout=timeout,
    )
    if args.message:
        # The model was asked for the body only, so the author's title leads.
        message = f"{args.message}\n\n{message}".rstrip() + "\n"

    return finish(message, ticket_refs, ticket_pattern, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())


if __name__ == "__main__":
    sys.exit(main())
