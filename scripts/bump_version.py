#!/usr/bin/env python
"""Bump the version and roll the changelog. Standard library only.

Used by .github/workflows/publish.yml so that every release run picks the next
version automatically instead of asking a human to type one.

    python scripts/bump_version.py --level patch            # 0.2.0 -> 0.2.1
    python scripts/bump_version.py --level minor            # 0.2.1 -> 0.3.0
    python scripts/bump_version.py --level patch --dry-run  # print, change nothing
    python scripts/bump_version.py --level patch --dev 42   # 0.2.1.dev42, no changelog

`--dev` produces a throwaway version for TestPyPI rehearsals: the module version
is bumped in the working tree but the changelog is left alone, because that build
is never released.

Prints the new version to stdout, and appends `version=<new>` to $GITHUB_OUTPUT
when running inside GitHub Actions.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys

REPO = "https://github.com/alegauss/commitclerk"
MODULE = "commitclerk/__init__.py"
CHANGELOG = "CHANGELOG.md"

# The trailing [^"]* tolerates a rehearsal suffix such as .dev42: a TestPyPI run
# leaves one behind in the working tree, and the next run must still parse it.
_VERSION_RE = re.compile(r'^__version__ = "(\d+)\.(\d+)\.(\d+)[^"]*"$', re.MULTILINE)
_HEADING_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)
_UNRELEASED_LINK_RE = re.compile(r"^\[Unreleased\]: .*$", re.MULTILINE)
_EMPTY_NOTE = "_Maintenance release: no user-facing changes were recorded._"


def read_version(text: str) -> tuple[int, int, int]:
    match = _VERSION_RE.search(text)
    if not match:
        raise SystemExit(f"Could not find a `__version__ = \"X.Y.Z\"` line in {MODULE}.")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def bump(current: tuple[int, int, int], level: str) -> str:
    major, minor, patch = current
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def roll_changelog(text: str, new_version: str, date: str) -> str:
    """Move everything under ## [Unreleased] into a new released section."""
    start = text.find("## [Unreleased]")
    if start == -1:
        raise SystemExit(f"No `## [Unreleased]` section in {CHANGELOG}.")

    body_start = start + len("## [Unreleased]")
    next_heading = text.find("\n## ", body_start)
    end = len(text) if next_heading == -1 else next_heading

    body = text[body_start:end].strip("\n")
    if not body.strip():
        print(f"warning: {CHANGELOG} has an empty Unreleased section", file=sys.stderr)
        body = _EMPTY_NOTE

    previous = _HEADING_RE.search(text[end:])
    new_section = (
        "## [Unreleased]\n\n"
        f"## [{new_version}] - {date}\n\n"
        f"{body}\n"
    )
    text = text[:start] + new_section + text[end:]

    # Point the Unreleased comparison at the new tag and add a link for it.
    if previous:
        prev_version = previous.group(1)
        compare = f"[{new_version}]: {REPO}/compare/v{prev_version}...v{new_version}"
    else:
        compare = f"[{new_version}]: {REPO}/releases/tag/v{new_version}"

    replacement = f"[Unreleased]: {REPO}/compare/v{new_version}...HEAD\n{compare}"
    text, count = _UNRELEASED_LINK_RE.subn(replacement, text, count=1)
    if count == 0:
        print(f"warning: no `[Unreleased]:` link definition found in {CHANGELOG}", file=sys.stderr)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="Bump the version and roll the changelog.")
    parser.add_argument(
        "--level",
        choices=("patch", "minor", "major"),
        default="patch",
        help="Which part of the version to increment (default: patch).",
    )
    parser.add_argument(
        "--dev",
        default=None,
        help="Build a throwaway X.Y.Z.devN version and leave the changelog untouched.",
    )
    parser.add_argument(
        "--date",
        default=datetime.date.today().isoformat(),
        help="Release date for the changelog heading (default: today).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the result, write nothing.")
    args = parser.parse_args()

    with open(MODULE, encoding="utf-8") as handle:
        module_text = handle.read()

    current = read_version(module_text)
    new_version = bump(current, args.level)
    written_version = f"{new_version}.dev{args.dev}" if args.dev else new_version

    print(f"{'.'.join(str(p) for p in current)} -> {written_version}")

    if args.dry_run:
        return 0

    new_module_text = _VERSION_RE.sub(f'__version__ = "{written_version}"', module_text, count=1)
    with open(MODULE, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(new_module_text)

    # A .devN build is a rehearsal, never a release: the changelog stays put.
    if not args.dev:
        with open(CHANGELOG, encoding="utf-8") as handle:
            changelog_text = handle.read()
        with open(CHANGELOG, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(roll_changelog(changelog_text, new_version, args.date))

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"version={written_version}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
