"""Reading the repository. The only module that runs git.

Nothing here ever writes: the commit itself is made by the CLI, and staging is
the user's business (see the non-goals in docs/ROADMAP.md).
"""

from __future__ import annotations

import subprocess

from .diffing import truncate

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


def get_staged_files() -> list[str]:
    result = run(["git", "diff", "--staged", "--name-only"], check=False)
    return [line for line in result.stdout.splitlines() if line.strip()]

