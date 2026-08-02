#!/usr/bin/env python
"""Concatenate the `commitclerk` package into one standalone script.

"One file you can read before you trust it near your source code" is the product's
promise, and the package split would have broken it. So the package is the source
and `dist/commitclerk.py` is the artifact: same code, no imports of its own beyond
the standard library, runnable straight after a `curl`.

    python scripts/build_single_file.py            # write dist/commitclerk.py
    python scripts/build_single_file.py --check     # fail if it is out of date

The `--check` mode is what CI runs, so a source change that forgets to rebuild is
caught in review rather than shipped as a stale download.

Standard library only, like the tool itself.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "commitclerk"
OUTPUT = ROOT / "dist" / "commitclerk.py"

# Dependency order, not alphabetical: each module may only use the ones above it.
# `__init__.py` and `__main__.py` are deliberately absent — the artifact needs no
# re-export layer and gets its own entry point at the bottom.
MODULES = ("config.py", "context.py", "diffing.py", "files.py", "history.py",
           "gitio.py", "trailers.py", "prompt.py", "providers.py", "cli.py")

BANNER = """#!/usr/bin/env python
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
"""

_IMPORT_RE = re.compile(r"^(?:import|from)\s+\S")
_LOCAL_IMPORT_RE = re.compile(r"^from\s+\.")
_FUTURE_RE = re.compile(r"^from\s+__future__\s+import")


def module_docstring_end(lines: list[str]) -> int:
    """Index just past a leading triple-quoted docstring, or 0 if there is none."""
    if not lines or not lines[0].lstrip().startswith('"""'):
        return 0
    if lines[0].count('"""') >= 2:  # single-line docstring
        return 1
    for i in range(1, len(lines)):
        if '"""' in lines[i]:
            return i + 1
    return 0


def strip_module(path: pathlib.Path) -> tuple[list[str], list[str]]:
    """A module's body without its docstring or imports, plus its stdlib imports."""
    lines = path.read_text(encoding="utf-8").splitlines()
    lines = lines[module_docstring_end(lines):]

    imports: list[str] = []
    body: list[str] = []
    pending: list[str] | None = None  # a `from x import (` still waiting for its `)`
    depth = 0

    for line in lines:
        if pending is not None:
            pending.append(line)
            depth += line.count("(") - line.count(")")
            if depth <= 0:
                if not _LOCAL_IMPORT_RE.match(pending[0]):
                    imports.extend(pending)
                pending = None
            continue

        if _FUTURE_RE.match(line):
            continue
        if _IMPORT_RE.match(line):
            depth = line.count("(") - line.count(")")
            if depth > 0:  # parenthesised, continues on the next lines
                pending = [line]
                continue
            if not _LOCAL_IMPORT_RE.match(line):
                imports.append(line)
            continue
        body.append(line)

    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return body, imports


def build() -> str:
    docstring = (PACKAGE / "__init__.py").read_text(encoding="utf-8").splitlines()
    docstring = docstring[:module_docstring_end(docstring)]

    version = ""
    for line in (PACKAGE / "__init__.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            version = line
            break
    if not version:
        raise SystemExit("no __version__ found in commitclerk/__init__.py")

    bodies: list[list[str]] = []
    imports: set = set()
    for name in MODULES:
        body, module_imports = strip_module(PACKAGE / name)
        bodies.append([f"# --- from commitclerk/{name} " + "-" * (48 - len(name)), ""] + body)
        imports.update(module_imports)

    parts = [BANNER, "\n".join(docstring), "", "from __future__ import annotations", ""]
    parts += sorted(imports)
    parts += ["", version, ""]
    for body in bodies:
        parts += ["", "\n".join(body), ""]
    parts += ['', 'if __name__ == "__main__":', "    sys.exit(main())", ""]

    text = "\n".join(parts)
    # Collapse runs of blank lines to the two PEP 8 wants between definitions.
    return re.sub(r"\n{4,}", "\n\n\n", text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit non-zero if the artifact is missing or stale.",
    )
    args = parser.parse_args()

    built = build()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current == built:
            print(f"{OUTPUT.relative_to(ROOT)} is up to date.")
            return 0
        print(
            f"{OUTPUT.relative_to(ROOT)} is out of date. "
            "Run: python scripts/build_single_file.py",
            file=sys.stderr,
        )
        return 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(built, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({len(built.splitlines())} lines).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
