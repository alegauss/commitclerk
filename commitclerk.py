#!/usr/bin/env python
"""commitclerk - AI-powered git commit messages.

Generates a commit message (short imperative title + bulleted summary body)
from the staged diff using the OpenAI Chat Completions API.

Reads the API key from OPENAI_API_KEY. No third-party dependencies.

Usage (installed as `clerk`, or run the file directly with `python commitclerk.py`):
    clerk                       # AI writes the whole message
    clerk -m "docs: fix X"      # use this exact title; AI writes only the body
    clerk --dry-run             # print message, do not commit
    clerk --model gpt-4o-mini

Environment:
    OPENAI_API_KEY   required
    OPENAI_MODEL     optional, overrides default model

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
import subprocess
import sys
import urllib.error
import urllib.request

__version__ = "0.2.1"

API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
MAX_DIFF_CHARS = 60_000

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


def is_doc_only(files: list[str]) -> bool:
    return bool(files) and all(_is_doc(f) for f in files)


_RULES = """- Describe what THIS commit changes, not what the changed text says. Prose added to documentation (CHANGELOG, ROADMAP, README, *.md) often describes features in past/present tense that ALREADY shipped in earlier commits; never restate that as work implemented in this commit.
- Title: imperative mood, max 72 chars, no trailing period.
- Use a Conventional Commits prefix when applicable (feat:, fix:, chore:, refactor:, docs:, test:, build:, perf:). Documentation-only changes use docs:.
- Body: 2 to 6 bullets summarizing the WHY and key changes; describe intent and behaviour, not a file-by-file diff replay.
- Bullets start with '- ' on their own line.
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


def get_staged_files() -> list[str]:
    result = run(["git", "diff", "--staged", "--name-only"], check=False)
    return [line for line in result.stdout.splitlines() if line.strip()]


def truncate(diff: str, limit: int) -> str:
    if len(diff) <= limit:
        return diff
    return diff[:limit] + "\n\n[...diff truncated for context length...]"


def call_openai(
    api_key: str,
    model: str,
    diff: str,
    files: list[str],
    *,
    title: str | None = None,
    doc_only: bool = False,
) -> str:
    body_only = title is not None
    parts = ["Files changed:"] + [f"- {f}" for f in files]
    if doc_only:
        parts += ["", _DOC_ONLY_NOTE]
    if body_only:
        parts += ["", f"Commit title (already chosen by the author, do not repeat it): {title}"]
    parts += ["", "Unified diff:", diff]
    user_prompt = "\n".join(parts)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_prompt(body_only=body_only)},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"OpenAI API error {exc.code}: {body}")
    except urllib.error.URLError as exc:
        raise SystemExit(f"OpenAI API request failed: {exc}")
    return data["choices"][0]["message"]["content"].strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="clerk",
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
        "--model",
        default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        help=f"OpenAI model (default: {DEFAULT_MODEL} or $OPENAI_MODEL).",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=MAX_DIFF_CHARS,
        help="Truncate the diff to this many chars before sending.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY is not set.", file=sys.stderr)
        return 2

    diff = get_staged_diff()
    if not diff.strip():
        print("No staged changes. Run `git add <files>` first.", file=sys.stderr)
        return 1

    files = get_staged_files()
    doc_only = is_doc_only(files)
    diff = truncate(diff, args.max_chars)

    if args.message:
        body = call_openai(api_key, args.model, diff, files, title=args.message, doc_only=doc_only)
        message = f"{args.message}\n\n{body}".rstrip() + "\n"
    else:
        message = call_openai(api_key, args.model, diff, files, doc_only=doc_only)

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
