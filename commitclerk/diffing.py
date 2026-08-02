"""Shaping a unified diff to fit a budget without hiding anything.

Pure string work: no git, no network, no provider. Every function here is a
candidate for a golden fixture test, which is why they take text and return text.
"""

from __future__ import annotations

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

