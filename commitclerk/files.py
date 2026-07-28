"""Classifying the files in a commit, and the documentation guard.

The founding idea of the tool lives here: prose that describes shipped work is
not evidence that this commit implements it.
"""

from __future__ import annotations

from .diffing import chunk_path, count_changes, split_diff

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

