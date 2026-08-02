"""The command line: parse flags, gather context, print, commit."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from . import __version__
from .diffing import MAX_DIFF_CHARS, budget_diff, demote_diff
from .files import classify_files, doc_guard_note, scope_note
from .gitio import (
    get_recent_commits,
    get_staged_diff,
    get_staged_files,
    get_staged_summary,
    get_unstaged_files,
    partially_staged,
    unstaged_warning,
)
from .history import HISTORY_DEPTH, MIN_COMMITS, house_style, known_scopes
from .providers import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    PROVIDERS,
    REQUEST_TIMEOUT,
    RETRY_ATTEMPTS,
    api_key_for,
    base_url_error,
    call_model,
    missing_key_env,
    resolve_base,
    resolve_model,
    resolve_provider,
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
        help=f"Do not read the last {HISTORY_DEPTH} commits to match this repo's own "
             "conventions (types, scopes, body shape, language). Nothing but subjects "
             "and bodies is read, and nothing leaves the machine that the diff would "
             "not already send.",
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
    # Subtracted from the diff budget, not added on top of it: the extra context is
    # worth a few hundred characters of diff, but it must not silently raise what
    # the user asked to send.
    context_cost = len(house) + len(scope)
    diff = budget_diff(demote_diff(diff, classes), max(0, args.max_chars - context_cost))

    if args.message:
        body = call_model(
            spec, api_key, model, diff, files, title=args.message, guard=guard,
            summary=summary, classes=classes, house_style=house, scope=scope,
            base=base, timeout=args.timeout,
        )
        message = f"{args.message}\n\n{body}".rstrip() + "\n"
    else:
        message = call_model(
            spec, api_key, model, diff, files, guard=guard,
            summary=summary, classes=classes, house_style=house, scope=scope,
            base=base, timeout=args.timeout,
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
