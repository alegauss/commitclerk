#!/usr/bin/env python
"""commitclerk - AI-powered git commit messages.

Generates a commit message (short imperative title + bulleted summary body)
from the staged diff by calling an LLM provider.

Reads the API key from the provider's key variable (OPENAI_API_KEY for the
default provider). No third-party dependencies.

Usage (installed as `clerk`, `commitclerk` or `git clerk`, or run the file
directly with `python commitclerk.py`):
    clerk                       # AI writes the whole message
    clerk -m "docs: fix X"      # use this exact title; AI writes only the body
    clerk --dry-run             # print message, do not commit
    clerk --model gpt-4o-mini
    clerk --provider anthropic  # select the API provider
    clerk --provider ollama     # local model, no API key, nothing leaves the box
    clerk --timeout 180         # give a slow local model more room
    clerk --base-url http://localhost:11434/v1   # any OpenAI-compatible endpoint
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

Why the doc-only handling: this script only sees the staged diff, so when a
commit just adds prose to CHANGELOG/ROADMAP/README that *describes* a feature,
the model used to echo it as "feat: implement <feature>" even though the feature
shipped in an earlier commit. The rules below (and the -m override) keep the
message about what THIS commit actually changes.
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
import urllib.error
import urllib.request

__version__ = "0.2.1"

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"
DEFAULT_OLLAMA_MODEL = "qwen2.5-coder"
DEFAULT_PROVIDER = "openai"
MAX_DIFF_CHARS = 60_000
# The change summary is one line per file: dense enough to always send, but a
# thousand-file commit still needs a ceiling.
MAX_SUMMARY_CHARS = 2_000
# Classes whose diff body is never worth budget: the model is told not to narrate
# them, so sending thousands of lines only crowds out the files that matter.
DEMOTED_CLASSES = ("generated", "vendor")
# ...but only once the body is big enough to be worth replacing. A two-line lockfile
# bump costs nothing, and a placeholder would be longer than the content.
DEMOTE_MIN_CHARS = 500
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


_RULES = """- Describe what THIS commit changes, not what the changed text says. Prose added to documentation (CHANGELOG, ROADMAP, README, *.md) often describes features in past/present tense that ALREADY shipped in earlier commits; never restate that as work implemented in this commit.
- Title: imperative mood, max 72 chars, no trailing period.
- Use a Conventional Commits prefix when applicable (feat:, fix:, chore:, refactor:, docs:, test:, build:, perf:). Documentation-only changes use docs:.
- Body: 2 to 6 bullets summarizing the WHY and key changes; describe intent and behaviour, not a file-by-file diff replay.
- Bullets start with '- ' on their own line.
- Read the change summary for facts the diff body cannot show. A rename is a move, never a rewrite; a mode change is a permission change; a binary file has a size change and no readable content, so never invent what is inside one.
- Each changed file is annotated with its class: code, test, docs, generated, config, vendor, binary. Pick the type prefix from the classes that are the point of the commit — only docs means docs:, only test means test:, only config or generated means chore: or build:. Never make a generated, vendored or binary file the subject of the message and never narrate its contents; when such files accompany a real change, mention them in at most one bullet as a consequence ("regenerated the lockfile").
- No markdown headers, no code fences, no emojis."""

_DOC_ONLY_NOTE = (
    "IMPORTANT: every file in this commit is documentation (no code changed). "
    "Use the docs: prefix and describe the documentation change itself "
    "(e.g. 'document X', 'record X in the changelog', 'remove completed tasks from the roadmap', "
    "'correct stale claims in README'). Do NOT say a feature was implemented or added: any feature "
    "described in the diff shipped in an earlier commit; this commit only writes it down."
)


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


def build_user_prompt(
    diff: str,
    files: list[str],
    *,
    title: str | None = None,
    doc_only: bool = False,
    summary: str = "",
    classes: dict | None = None,
) -> str:
    classes = classes or {}
    parts = ["Files changed:"] + [
        f"- {f} ({classes[f]})" if f in classes else f"- {f}" for f in files
    ]
    if classes:
        parts += [f"Class mix: {class_mix(classes)}"]
    if summary:
        # Before the diff, and outside its budget: when a large diff is trimmed
        # this is the part that still describes the whole change.
        parts += ["", "Change summary (git --stat --summary):", summary]
    if doc_only:
        parts += ["", _DOC_ONLY_NOTE]
    if title is not None:
        parts += ["", f"Commit title (already chosen by the author, do not repeat it): {title}"]
    parts += ["", "Unified diff:", diff]
    return "\n".join(parts)


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
    title: str | None = None,
    doc_only: bool = False,
    summary: str = "",
    classes: dict | None = None,
    base: str | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> str:
    payload = spec["payload"](
        model,
        _system_prompt(body_only=title is not None),
        build_user_prompt(
            diff, files, title=title, doc_only=doc_only, summary=summary, classes=classes
        ),
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
    classes = classify_files(files, diff)
    doc_only = is_doc_only(files)
    summary = get_staged_summary()
    # Demote before budgeting, so the space a lockfile was using is handed to the
    # files the commit is actually about.
    diff = budget_diff(demote_diff(diff, classes), args.max_chars)

    if args.message:
        body = call_model(
            spec, api_key, model, diff, files, title=args.message, doc_only=doc_only,
            summary=summary, classes=classes, base=base, timeout=args.timeout,
        )
        message = f"{args.message}\n\n{body}".rstrip() + "\n"
    else:
        message = call_model(
            spec, api_key, model, diff, files, doc_only=doc_only,
            summary=summary, classes=classes, base=base, timeout=args.timeout,
        )

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
