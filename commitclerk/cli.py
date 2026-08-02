"""The command line: parse flags, gather context, print, commit."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from . import __version__
from .config import PROJECT_CONFIG, ConfigError, env_value, layered, load_config
from .context import CONTEXT_FILE, context_note, context_path, read_context_file
from .deep import (
    DEEP_NOTE,
    SUMMARY_SYSTEM_PROMPT,
    summarize_diff,
    summary_user_prompt,
)
from .diffing import MAX_DIFF_CHARS, budget_diff, demote_diff, over_budget_paths
from .excludes import (
    clerkignore_path,
    exclusion_notice,
    excluded_paths,
    read_clerkignore,
)
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
    known_types,
    worked_examples,
)
from .offline import offline_message
from .secrets import redact_diff, redaction_notice, refusal_notice, scan_diff
from .trailers import (
    ASSISTED_TRAILER,
    DEFAULT_TICKET_PATTERN,
    TICKET_TRAILER,
    add_trailer,
    assisted_value,
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
    complete,
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


def _wants_examples(house_style_on, cli, project, user) -> bool:
    """Whether worked examples may be sent, given the fingerprint's own answer.

    The narrow half of one refusal: the fingerprint transmits counts and shapes,
    the examples transmit past commit message text verbatim, and a team can want
    the first without the second. Gated on the fingerprint rather than resolved
    beside it, because refusing the whole `git log` has already refused the
    examples -- `"examples": true` under `"house_style": false` would otherwise
    ask for text out of a history nothing read.
    """
    return bool(house_style_on and layered(cli, None, project, user, True))


def finish(
    message: str,
    ticket_refs,
    ticket_pattern: str,
    *,
    dry_run: bool,
    assisted: str = "",
) -> int:
    """Trailers, print, commit -- the tail the online and offline paths share.

    Both trailers are applied here, after the message exists and never through
    the model: one is read off the branch and one off the version and the model
    actually called, so the only thing that could go wrong is a paraphrase, and
    this way there is none. `--offline` gets both, the branch name being as
    local as everything else on that path.

    `Refs:` first. That one is about the work; `Assisted-by:` is about how the
    message was written, and fixing the order here keeps it from becoming an
    accident of which branch of `main` ran.
    """
    if ticket_refs:
        key = ticket_key(get_branch_name(), ticket_pattern)
        if key:
            message = add_trailer(message, TICKET_TRAILER, key)
    if assisted:
        message = add_trailer(message, ASSISTED_TRAILER, assisted)

    if dry_run:
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


def call_target(args, project: dict, user: dict, provider: str) -> tuple:
    """(spec, api_key, model, base, "") for the endpoint to call, or (…, problem).

    Separated from `main` because `--offline` must not run any of it: resolving
    a provider that will never be called turns an unset key into an error on the
    one path that has no use for one.
    """
    spec = resolve_provider(provider)
    if spec is None:
        known = ", ".join(sorted(PROVIDERS))
        return None, None, None, None, (
            f"unknown provider '{provider}'. Known providers: {known}"
        )
    missing = missing_key_env(spec)
    if missing:
        return None, None, None, None, f"{missing} is not set"

    model = resolve_model(spec, args.model, project.get("model"), user.get("model"))
    base = resolve_base(spec, args.base_url, project.get("base_url"), user.get("base_url"))
    problem = base_url_error(base)
    if problem:
        return None, None, None, None, problem
    return spec, api_key_for(spec), model, base, ""


def deepen(
    diff: str,
    budget: int,
    spec: dict,
    api_key: str | None,
    model: str,
    *,
    base: str | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> tuple[str, str]:
    """The map half of `--deep`: (diff with summaries, the note that explains them).

    Asked of the already-demoted diff and against the real budget, so the
    question is the exact one the allocator is about to answer -- which files
    would lose their tail. A commit that already fits names none of them and
    spends nothing, which is what makes the flag safe to leave on in a config
    file. The note comes back empty when no summary was obtained, because a
    notation nothing uses is only budget spent on confusing the model.
    """
    oversized = over_budget_paths(diff, budget)
    if not oversized:
        return diff, ""
    print(
        f"Summarizing {len(oversized)} oversized file(s) "
        f"in {len(oversized)} extra request(s).",
        file=sys.stderr,
    )

    def summarize(path: str, chunk: str) -> str:
        try:
            return complete(
                spec, api_key, model,
                SUMMARY_SYSTEM_PROMPT, summary_user_prompt(path, chunk),
                base=base, timeout=timeout,
            )
        # `post_json` reports a fatal API error by raising this. One file's
        # summary is not worth the commit: say so, and let the file be trimmed
        # exactly as it would have been without the flag.
        except SystemExit as exc:
            print(f"Could not summarize {path} ({exc}).", file=sys.stderr)
            return ""

    diff, summarized = summarize_diff(diff, oversized, summarize)
    return diff, DEEP_NOTE if summarized else ""


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
        "--deep",
        action="store_true",
        default=None,
        help="Summarize each file too large for the diff budget in its own cheap request, "
             "then write the message from those summaries plus the smaller files' real "
             "diffs. Costs one extra request per oversized file, and nothing at all when "
             "the whole diff already fits.",
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
    parser.add_argument(
        "--no-examples",
        action="store_true",
        default=None,
        help="Do not send past commit message text. Turns off the worked examples "
             "drawn from earlier commits that touched the same files, and keeps the "
             "house-style fingerprint, which reports only counts and shapes. Implied "
             "by --no-house-style.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        default=None,
        help="Write the message locally with no API call, no key and no network. The "
             "type comes from the file classes, the scope from the workspace manifest "
             "and the bullets are grouped by directory. It never guesses feat: or "
             "fix:, which state intent nothing local can see, so it is a draft rather "
             "than a replacement - and it always beats an error when you are offline.",
    )
    parser.add_argument(
        "--redact",
        action="store_true",
        default=None,
        help="Instead of refusing, mask every suspected secret in the request and "
             "carry on. The commit is unchanged and still contains them: this "
             "protects what is sent, not what is committed.",
    )
    parser.add_argument(
        "--no-scan",
        action="store_true",
        default=None,
        help="Do not scan the staged diff for secrets before sending it. Turns off "
             "--redact along with it, there being nothing left to mask.",
    )
    args = parser.parse_args()

    root = get_repo_root()
    try:
        project, user, notices = load_config(root)
        # Parsed on every path, applied only where there is something to
        # withhold: a malformed .clerkignore is a mistake worth reporting even
        # on a run that was never going to transmit anything.
        rules = read_clerkignore(clerkignore_path(root))
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
    examples_on = _wants_examples(
        house_style_on, False if args.no_examples else None,
        project.get("examples"), user.get("examples"),
    )
    scan_on = layered(
        False if args.no_scan else None, None,
        project.get("scan"), user.get("scan"), True,
    )
    deep_on = layered(
        True if args.deep else None, None, project.get("deep"), user.get("deep"), False,
    )
    ticket_pattern = layered(
        None, None,
        project.get("ticket_pattern"), user.get("ticket_pattern"), DEFAULT_TICKET_PATTERN,
    )
    ticket_refs = layered(
        None, None, _wants_refs(project), _wants_refs(user), False,
    )
    assisted_by = layered(
        None, None, project.get("assisted_by"), user.get("assisted_by"), False,
    )
    if ticket_refs and compile_ticket_pattern(ticket_pattern) is None:
        print(
            f"Error: 'ticket_pattern' is not a valid regular expression: {ticket_pattern}.",
            file=sys.stderr,
        )
        return 2

    # Not resolved at all under --offline: that path makes no request, so a
    # missing key is not a problem it has, and refusing to write a message over
    # one would reintroduce the outage this flag exists to survive.
    spec = api_key = model = base = None
    if not args.offline:
        spec, api_key, model, base, problem = call_target(args, project, user, provider)
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

    if args.offline:
        # No secret scan on this path: that scan exists to stop a transmission,
        # and there is none. Refusing a commit that sends nothing would make
        # this a pre-commit hook, which is a different tool.
        records = get_recent_commits() if house_style_on else []
        return finish(
            offline_message(
                files, classes, get_staged_summary(),
                title=args.message,
                types=known_types(records) if records else None,
                scopes=known_scopes(records) if len(records) >= MIN_COMMITS else None,
            ),
            ticket_refs, ticket_pattern, dry_run=args.dry_run,
            # No model was called, and saying one was is the lie this whole
            # tool is built to not tell.
            assisted=assisted_value(__version__) if assisted_by else "",
        )

    # Before the scan, not after: content that is never transmitted has nothing
    # to refuse over, which is what makes .clerkignore the escape hatch for a
    # false positive rather than one more thing --no-scan has to switch off.
    hidden = excluded_paths(files, rules)
    if hidden:
        diff = demote_diff(diff, {}, (), excluded=set(hidden))
        print(exclusion_notice(hidden), file=sys.stderr)

    # Before every request, and on the diff as staged rather than as trimmed: a
    # scan placed after demotion or the budget would clear a payload that
    # `--deep`'s own calls have already carried.
    findings = scan_diff(diff, classes) if scan_on else []
    if findings:
        if not args.redact:
            print(refusal_notice(findings), file=sys.stderr)
            return 3
        diff, masked = redact_diff(diff, classes)
        print(redaction_notice(masked), file=sys.stderr)

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
    examples = worked_examples(records, files) if examples_on else ""
    author = context_note(read_context_file(context_path(root)), args.context)

    context = {
        "guard": guard,
        "summary": summary,
        "classes": classes,
        "house_style": house,
        "examples": examples,
        "scope": scope,
        "context": author,
        "excluded": hidden,
    }
    if args.message:
        context["title"] = args.message

    # Subtracted from the diff budget, not added on top of it: the extra context is
    # worth a couple of thousand characters of diff, but it must not silently raise
    # what the user asked to send.
    spent = len(house) + len(scope) + len(examples) + len(author)
    budget = max(0, max_chars - spent)
    diff = demote_diff(diff, classes)

    if deep_on:
        diff, note = deepen(
            diff, budget, spec, api_key, model, base=base, timeout=timeout,
        )
        if note:
            context["deep"] = note
            budget = max(0, budget - len(note))

    diff = budget_diff(diff, budget)

    message = call_model(
        spec, api_key, model, diff, files,
        context=context, base=base, timeout=timeout,
    )
    if args.message:
        # The model was asked for the body only, so the author's title leads.
        message = f"{args.message}\n\n{message}".rstrip() + "\n"

    return finish(
        message, ticket_refs, ticket_pattern, dry_run=args.dry_run,
        assisted=assisted_value(__version__, model) if assisted_by else "",
    )



if __name__ == "__main__":
    sys.exit(main())
