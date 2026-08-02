"""commitclerk - AI-powered git commit messages.

Generates a commit message (short imperative title + bulleted summary body)
from the staged diff by calling an LLM provider.

Reads the API key from the provider's key variable (OPENAI_API_KEY for the
default provider). No third-party dependencies.

Usage (installed as `clerk`, `commitclerk` or `git clerk`, or run the
single-file build with `python commitclerk.py`):
    clerk                       # AI writes the whole message
    clerk -m "docs: fix X"      # use this exact title; AI writes only the body
    clerk --dry-run             # print message, do not commit
    clerk --model gpt-4o-mini
    clerk --provider anthropic  # select the API provider
    clerk --provider ollama     # local model, no API key, nothing leaves the box
    clerk --timeout 180         # give a slow local model more room
    clerk --deep                # summarize each file too big for the budget
    clerk --base-url http://localhost:11434/v1   # any OpenAI-compatible endpoint
    clerk --no-house-style      # do not copy this repo's own commit conventions
    clerk --no-examples         # keep the fingerprint, send no past message text
    clerk --context "reverts the caching experiment"   # why, in one sentence
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

Configuration files (JSON; keys provider, model, base_url, timeout, max_chars,
house_style, examples, deep, ticket_refs, ticket_pattern). A setting is taken
from the first place that has it:
    a flag  >  the environment  >  ./.clerk.json  >  ~/.config/clerk/config.json
    >  the built-in default
`.clerk.json` is looked for at the repository root, so the tool behaves the same
from any subdirectory, and is meant to be committed: it is how a team stops
retyping its own convention. API keys are read from the environment only.

`.clerk/context.md` under the repository root carries standing facts the diff
cannot show, read verbatim on every run; `--context "<note>"` says the same
thing for one commit. Both only add to the prompt - see `context.py`.

With ticket_refs on, the issue key in the branch name (feat/PROJ-123-thing)
is appended to the finished message as a `Refs: PROJ-123` trailer. Off by
default, and never sent to the model - see `trailers.py`.

Why the doc-only handling: this tool only sees the staged diff, so when a
commit just adds prose to CHANGELOG/ROADMAP/README that *describes* a feature,
the model used to echo it as "feat: implement <feature>" even though the feature
shipped in an earlier commit. The rules in `prompt.py` (and the -m override)
keep the message about what THIS commit actually changes.

`history.py` reads the last 200 commit subjects, bodies and touched paths: it
measures the types, scopes, body shape and language this repo actually uses, and
picks the past commits that overlap the current diff as worked examples, so the
message written belongs in this history rather than being generically correct.
`files.py` walks
each staged file up to its nearest workspace manifest, so a monorepo change
confined to one package is scoped to it.

For a commit no budget can fit, `--deep` (`deep.py`) summarizes each oversized
file in its own cheap request and writes the message from those summaries plus
the smaller files' real diffs, so the tail of a 5 000-line change is described
rather than trimmed away. One extra request per oversized file, none when the
diff already fits, and a summary that fails leaves that file to be trimmed as
usual - never invented.

The source is a package; `dist/commitclerk.py` is the same code concatenated into
one file by `scripts/build_single_file.py`, for people who would rather read and
copy a single script than install anything.
"""

from __future__ import annotations

__version__ = "0.2.1"

# Re-exported so this package's namespace matches the single-file build's exactly:
# in `dist/commitclerk.py` these are plain module-level imports, and the tests
# patch them (`commitclerk.time.sleep`, `commitclerk.urllib.request.urlopen`). Same
# names here means the same test suite proves both shapes.
import json  # noqa: E402, F401
import os  # noqa: E402, F401
import random  # noqa: E402, F401
import re  # noqa: E402, F401
import subprocess  # noqa: E402, F401
import sys  # noqa: E402, F401
import time  # noqa: E402, F401
import unicodedata  # noqa: E402, F401
import urllib.error  # noqa: E402, F401
import urllib.request  # noqa: E402, F401

from .config import (  # noqa: E402
    PROJECT_CONFIG,
    SETTINGS,
    USER_CONFIG,
    ConfigError,
    env_value,
    layered,
    load_config,
    project_config_path,
    read_config,
    user_config_path,
)
from .context import (  # noqa: E402
    CONTEXT_FILE,
    MAX_CONTEXT_CHARS,
    context_note,
    context_path,
    read_context_file,
)
from .diffing import (  # noqa: E402
    DEMOTE_MIN_CHARS,
    DEMOTED_CLASSES,
    MAX_DIFF_CHARS,
    budget_diff,
    chunk_path,
    count_changes,
    demote_diff,
    over_budget_paths,
    split_diff,
    truncate,
)
from .deep import (  # noqa: E402
    DEEP_NOTE,
    SUMMARY_INPUT_CHARS,
    SUMMARY_LINE_CHARS,
    SUMMARY_MARK,
    SUMMARY_MAX_LINES,
    SUMMARY_SYSTEM_PROMPT,
    clean_summary,
    summarize_diff,
    summary_block,
    summary_user_prompt,
)
from .files import (  # noqa: E402
    FILE_CLASSES,
    _is_doc,
    binary_paths,
    class_mix,
    classify,
    classify_files,
    doc_guard_note,
    doc_line_share,
    is_doc_only,
    package_root,
    package_span,
    scope_note,
)
from .history import (  # noqa: E402
    FIELD_SEP,
    HISTORY_DEPTH,
    MAX_EXAMPLE_BODY_CHARS,
    MAX_EXAMPLES,
    MAX_EXAMPLES_CHARS,
    MAX_HOUSE_STYLE_CHARS,
    MIN_COMMITS,
    MIN_PATH_OVERLAP,
    RECORD_SEP,
    body_shape,
    bullet_marker,
    commit_paths,
    dominant_language,
    house_style,
    known_scopes,
    parse_commit,
    path_tokens,
    similar_commits,
    split_records,
    strip_prefix,
    strip_trailers,
    subject_type_scope,
    trailer_keys,
    worked_examples,
)
from .gitio import (  # noqa: E402
    MAX_SUMMARY_CHARS,
    get_branch_name,
    get_recent_commits,
    get_repo_root,
    get_staged_diff,
    get_staged_files,
    get_staged_summary,
    get_unstaged_files,
    partially_staged,
    run,
    unstaged_warning,
)
from .prompt import _system_prompt, build_user_prompt  # noqa: E402
from .trailers import (  # noqa: E402
    DEFAULT_TICKET_PATTERN,
    TICKET_TRAILER,
    add_trailer,
    compile_ticket_pattern,
    ticket_key,
)
from .providers import (  # noqa: E402
    ANTHROPIC_MAX_TOKENS,
    ANTHROPIC_VERSION,
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_PROVIDER,
    DROPPABLE_PARAMS,
    PROTECTED_PARAMS,
    PROVIDERS,
    REQUEST_TIMEOUT,
    RETRY_ATTEMPTS,
    RETRY_BASE_DELAY,
    RETRY_MAX_DELAY,
    RETRY_STATUSES,
    _anthropic_extract,
    _anthropic_payload,
    _openai_extract,
    _openai_payload,
    api_key_for,
    base_url_error,
    call_model,
    complete,
    missing_key_env,
    post_json,
    provider_url,
    repair_payload,
    resolve_base,
    resolve_model,
    resolve_provider,
    retry_after_seconds,
    retry_delay,
    suggested_replacement,
)

from .cli import (  # noqa: E402  (last: it imports the rest)
    _wants_examples,
    _wants_refs,
    deepen,
    main,
    prog_name,
)

__all__ = [
    "__version__",
    "main",
    "prog_name",
    "PROVIDERS",
    "PROJECT_CONFIG",
    "ConfigError",
    "layered",
    "load_config",
    "read_config",
    "user_config_path",
    "add_trailer",
    "ticket_key",
    "get_branch_name",
    "context_note",
    "read_context_file",
    "call_model",
    "classify",
    "classify_files",
    "doc_guard_note",
    "house_style",
    "known_scopes",
    "worked_examples",
    "scope_note",
    "get_recent_commits",
    "budget_diff",
    "demote_diff",
    "over_budget_paths",
    "summarize_diff",
    "get_staged_diff",
    "get_staged_files",
    "get_staged_summary",
    "post_json",
]
