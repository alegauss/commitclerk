"""Map-reduce for the commits no budget can fit.

A fair split of 60 000 characters across a dozen large files shows the model the
first few percent of each, and everything after that is a `[... N lines
truncated ...]` marker the message can only be silent about. Trimming harder is
not the answer, and neither is a bigger budget: a vendored upgrade or a
formatter run is larger than any context window worth paying for.

So: one cheap call per oversized file, reading that file's whole diff and
answering in at most two lines, then the ordinary single call writing the
message from those summaries plus the small files' real diffs. It costs N+1
requests, which is exactly why it is opt-in and never the default.

No network here. `summarize_diff` takes the call as an argument, so this module
stays testable string work and the caller keeps every decision about failure.
"""

from __future__ import annotations

from .diffing import _split_header, chunk_path, count_changes, split_diff, truncate
from .fencing import FENCE_RULE, fence

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
    "say exactly that in one line.\n"
    # This call reads a whole file's diff, unfiltered and unbudgeted. It is the
    # most exposed request the tool makes, not the least, and being cheap is no
    # reason to frame it with weaker rules than the one that writes the message.
    + FENCE_RULE
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
    return "\n".join([
        f"File: {path}",
        "",
        "Unified diff for this file:",
        fence("FILE DIFF", truncate(chunk, limit)),
    ])


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
