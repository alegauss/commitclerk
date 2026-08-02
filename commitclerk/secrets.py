"""The pre-flight scan: refuse to send a staged secret to a third-party API.

This sits *upstream* of every secret-scanning hook a team already runs, because
the request leaves before the commit exists -- and unlike the commit, a
transmission cannot be taken back with `git reset`.

Pure string work, standard library only: these functions take a diff and the
file classes and return findings or a rewritten diff. Nothing here reads a file,
calls git, or decides what the CLI does about what it found.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import NamedTuple

from .diffing import chunk_path, split_diff

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
