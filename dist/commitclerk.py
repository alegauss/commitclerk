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
    clerk --base-url http://localhost:11434/v1   # any OpenAI-compatible endpoint
    clerk --no-house-style      # do not copy this repo's own commit conventions
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

The source is a package; `dist/commitclerk.py` is the same code concatenated into
one file by `scripts/build_single_file.py`, for people who would rather read and
copy a single script than install anything.
"""

from __future__ import annotations

import argparse
import json
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


def demote_diff(diff: str, classes: dict, classes_to_demote: tuple = DEMOTED_CLASSES) -> str:
    """Replace the body of files that can never be the subject with one line.

    A `package-lock.json` bump is thousands of lines the model has been told not to
    narrate, competing for the same budget as the three-line fix that is the actual
    commit. The header stays — silently dropping a file would repeat the mistake
    head-truncation used to make — and the counts stay, because "regenerated the
    lockfile (+8412 -3110)" is the whole of what a reader needs.
    """
    if not classes:
        return diff
    out = []
    for chunk in split_diff(diff):
        path = chunk_path(chunk)
        klass = classes.get(path) if path else None
        header, body = _split_header(chunk)
        body_text = "".join(body)
        if klass in classes_to_demote and len(body_text) > DEMOTE_MIN_CHARS:
            added, removed = count_changes(body_text)
            out.append(
                "".join(header)
                + f"[... {klass} file, +{added} -{removed}, contents not shown ...]\n"
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

    headers, bodies = [], []
    for chunk in chunks:
        header, body = _split_header(chunk)
        headers.append(header)
        bodies.append(body)

    reserved = sum(len("".join(h)) + _MARKER_RESERVE for h in headers)
    taken = _allocate_round_robin(bodies, limit - reserved)

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
    parts += ["Files changed:"] + [
        f"- {f} ({classes[f]})" if f in classes else f"- {f}" for f in files
    ]
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


def resolve_model(spec: dict, cli_model: str | None = None) -> str:
    """Model to call: CLI flag > provider's env var > provider default."""
    if cli_model:
        return cli_model
    env = spec.get("model_env")
    return (os.environ.get(env) if env else None) or spec["default_model"]


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


def resolve_base(spec: dict, cli_base: str | None = None) -> str:
    """Base URL to call: CLI flag > provider's env var > provider default.

    Most vendors clone the OpenAI wire format, so pointing this at Ollama,
    LM Studio, vLLM, OpenRouter, Groq, Together or Azure needs no new adapter.
    """
    if cli_base:
        return cli_base
    env = spec.get("base_env")
    return (os.environ.get(env) if env else None) or spec["default_base"]


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
    payload = spec["payload"](
        model,
        _system_prompt(body_only=context.get("title") is not None),
        build_user_prompt(diff, files, **context),
    )

    headers = {"Content-Type": "application/json"}
    headers.update(spec["headers"](api_key))
    label = spec["label"]
    data = post_json(
        provider_url(spec, base),
        payload,
        headers,
        label=label,
        timeout=timeout,
    )

    text = spec["extract"](data).strip()
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
        "--provider",
        default=os.environ.get("CLERK_PROVIDER", DEFAULT_PROVIDER),
        choices=sorted(PROVIDERS),
        help=f"API provider (default: {DEFAULT_PROVIDER} or $CLERK_PROVIDER).",
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
        default=REQUEST_TIMEOUT,
        help=f"Seconds to wait for each API request (default: {REQUEST_TIMEOUT}). A slow "
             f"local model may need more. Transient failures are retried up to "
             f"{RETRY_ATTEMPTS - 1} times.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=MAX_DIFF_CHARS,
        help="Budget for the diff, in characters. Oversized diffs are trimmed per file "
             "so every changed file stays visible to the model, and the contents of "
             "generated or vendored files are replaced by a one-line placeholder.",
    )
    parser.add_argument(
        "--no-house-style",
        action="store_true",
        help=f"Do not read the last {HISTORY_DEPTH} commits. Turns off both the "
             "house-style fingerprint (the types, scopes, body shape and language "
             "this repo uses) and the worked examples drawn from past commits that "
             "touched the same files. Use it to keep past commit message text off "
             "the wire, or when the history is not a style worth copying.",
    )
    args = parser.parse_args()

    spec = resolve_provider(args.provider)
    if spec is None:
        known = ", ".join(sorted(PROVIDERS))
        print(
            f"Error: unknown provider '{args.provider}'. Known providers: {known}.",
            file=sys.stderr,
        )
        return 2

    missing = missing_key_env(spec)
    if missing:
        print(f"Error: {missing} is not set.", file=sys.stderr)
        return 2
    api_key = api_key_for(spec)
    model = resolve_model(spec, args.model)

    base = resolve_base(spec, args.base_url)
    problem = base_url_error(base)
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
    summary = get_staged_summary()
    # Both read the raw diff: the guard's proportion must be measured before any
    # trimming, and demotion must happen before budgeting so the space a lockfile
    # was using is handed to the files the commit is actually about.
    guard = doc_guard_note(files, diff)
    records = [] if args.no_house_style else get_recent_commits()
    house = house_style(records)
    # None means no history was read, which is not the same as a history that shows
    # no scopes -- only the second is a reason for scope inference to stay quiet.
    vocabulary = known_scopes(records) if len(records) >= MIN_COMMITS else None
    scope = scope_note(files, vocabulary)
    examples = worked_examples(records, files)

    context = {
        "guard": guard,
        "summary": summary,
        "classes": classes,
        "house_style": house,
        "examples": examples,
        "scope": scope,
    }
    if args.message:
        context["title"] = args.message

    # Subtracted from the diff budget, not added on top of it: the extra context is
    # worth a couple of thousand characters of diff, but it must not silently raise
    # what the user asked to send.
    spent = len(house) + len(scope) + len(examples)
    diff = budget_diff(demote_diff(diff, classes), max(0, args.max_chars - spent))

    message = call_model(
        spec, api_key, model, diff, files,
        context=context, base=base, timeout=args.timeout,
    )
    if args.message:
        # The model was asked for the body only, so the author's title leads.
        message = f"{args.message}\n\n{message}".rstrip() + "\n"

    if args.dry_run:
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


if __name__ == "__main__":
    sys.exit(main())


if __name__ == "__main__":
    sys.exit(main())
