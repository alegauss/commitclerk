"""The command line: parse flags, gather context, print, commit."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from . import __version__
from .config import PROJECT_CONFIG, ConfigError, env_value, layered, load_config
from .context import CONTEXT_FILE, context_note, context_path, read_context_file
from .diffing import MAX_DIFF_CHARS, budget_diff, demote_diff
from .files import classify_files, doc_guard_note, scope_note
from .gitio import (
    get_branch_name,
    get_recent_commits,
    get_repo_root,
    get_staged_diff,
    get_staged_files,
    get_staged_summary,
    get_unstaged_files,
    partially_staged,
    unstaged_warning,
)
from .history import (
    HISTORY_DEPTH,
    MIN_COMMITS,
    house_style,
    known_scopes,
    worked_examples,
)
from .trailers import (
    DEFAULT_TICKET_PATTERN,
    TICKET_TRAILER,
    add_trailer,
    compile_ticket_pattern,
    ticket_key,
)
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

def _wants_refs(settings: dict) -> bool | None:
    """Whether one config file asks for the `Refs:` trailer, or None if it is silent.

    Naming a `ticket_pattern` is asking for the trailer, so a file does not have
    to say so twice; `ticket_refs` alone is for a project that wants the built-in
    pattern and nothing to configure. Either can be set to `false` to turn off
    what the file below it in the ladder turned on.
    """
    if "ticket_refs" in settings:
        return settings["ticket_refs"]
    return True if "ticket_pattern" in settings else None


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
        "--context",
        default=None,
        metavar="NOTE",
        help="One sentence of intent the diff cannot show, e.g. \"this reverts the "
             f"caching experiment\". Standing facts about the repository belong in "
             f"{CONTEXT_FILE} instead, which is read on every run.",
    )
    parser.add_argument(
        "--provider",
        default=None,
        choices=sorted(PROVIDERS),
        help=f"API provider (default: {DEFAULT_PROVIDER}, or $CLERK_PROVIDER, or "
             f"\"provider\" in {PROJECT_CONFIG}).",
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
        default=None,
        help=f"Seconds to wait for each API request (default: {REQUEST_TIMEOUT}). A slow "
             f"local model may need more. Transient failures are retried up to "
             f"{RETRY_ATTEMPTS - 1} times.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=None,
        help="Budget for the diff, in characters. Oversized diffs are trimmed per file "
             "so every changed file stays visible to the model, and the contents of "
             "generated or vendored files are replaced by a one-line placeholder.",
    )
    parser.add_argument(
        "--no-house-style",
        action="store_true",
        default=None,
        help=f"Do not read the last {HISTORY_DEPTH} commits. Turns off both the "
             "house-style fingerprint (the types, scopes, body shape and language "
             "this repo uses) and the worked examples drawn from past commits that "
             "touched the same files. Use it to keep past commit message text off "
             "the wire, or when the history is not a style worth copying.",
    )
    args = parser.parse_args()

    root = get_repo_root()
    try:
        project, user, notices = load_config(root)
    except ConfigError as exc:
        print(f"Error: {exc}.", file=sys.stderr)
        return 2
    for notice in notices:
        print(notice, file=sys.stderr)

    # Every setting below is resolved by the same five-rung ladder, in the order
    # `layered` documents: CLI > environment > project file > user file > default.
    provider = layered(
        args.provider, env_value("CLERK_PROVIDER"),
        project.get("provider"), user.get("provider"), DEFAULT_PROVIDER,
    )
    timeout = layered(
        args.timeout, None, project.get("timeout"), user.get("timeout"), REQUEST_TIMEOUT,
    )
    max_chars = layered(
        args.max_chars, None, project.get("max_chars"), user.get("max_chars"), MAX_DIFF_CHARS,
    )
    # The flag is negative and the setting is positive: passing --no-house-style
    # is the CLI saying `false`, and not passing it says nothing at all.
    house_style_on = layered(
        False if args.no_house_style else None, None,
        project.get("house_style"), user.get("house_style"), True,
    )
    ticket_pattern = layered(
        None, None,
        project.get("ticket_pattern"), user.get("ticket_pattern"), DEFAULT_TICKET_PATTERN,
    )
    ticket_refs = layered(
        None, None, _wants_refs(project), _wants_refs(user), False,
    )
    if ticket_refs and compile_ticket_pattern(ticket_pattern) is None:
        print(
            f"Error: 'ticket_pattern' is not a valid regular expression: {ticket_pattern}.",
            file=sys.stderr,
        )
        return 2

    spec = resolve_provider(provider)
    if spec is None:
        known = ", ".join(sorted(PROVIDERS))
        print(
            f"Error: unknown provider '{provider}'. Known providers: {known}.",
            file=sys.stderr,
        )
        return 2

    missing = missing_key_env(spec)
    if missing:
        print(f"Error: {missing} is not set.", file=sys.stderr)
        return 2
    api_key = api_key_for(spec)
    model = resolve_model(spec, args.model, project.get("model"), user.get("model"))

    base = resolve_base(spec, args.base_url, project.get("base_url"), user.get("base_url"))
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
    records = get_recent_commits() if house_style_on else []
    house = house_style(records)
    # None means no history was read, which is not the same as a history that shows
    # no scopes -- only the second is a reason for scope inference to stay quiet.
    vocabulary = known_scopes(records) if len(records) >= MIN_COMMITS else None
    scope = scope_note(files, vocabulary)
    examples = worked_examples(records, files)
    author = context_note(read_context_file(context_path(root)), args.context)

    context = {
        "guard": guard,
        "summary": summary,
        "classes": classes,
        "house_style": house,
        "examples": examples,
        "scope": scope,
        "context": author,
    }
    if args.message:
        context["title"] = args.message

    # Subtracted from the diff budget, not added on top of it: the extra context is
    # worth a couple of thousand characters of diff, but it must not silently raise
    # what the user asked to send.
    spent = len(house) + len(scope) + len(examples) + len(author)
    diff = budget_diff(demote_diff(diff, classes), max(0, max_chars - spent))

    message = call_model(
        spec, api_key, model, diff, files,
        context=context, base=base, timeout=timeout,
    )
    if args.message:
        # The model was asked for the body only, so the author's title leads.
        message = f"{args.message}\n\n{message}".rstrip() + "\n"

    # After the model, never through it: the key is read off the branch, so the
    # one thing that could go wrong is a paraphrase, and this way there is none.
    if ticket_refs:
        key = ticket_key(get_branch_name(), ticket_pattern)
        if key:
            message = add_trailer(message, TICKET_TRAILER, key)

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
