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
    clerk --base-url http://localhost:11434/v1   # any OpenAI-compatible endpoint
    clerk --no-house-style      # do not copy this repo's own commit conventions
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

Why the doc-only handling: this tool only sees the staged diff, so when a
commit just adds prose to CHANGELOG/ROADMAP/README that *describes* a feature,
the model used to echo it as "feat: implement <feature>" even though the feature
shipped in an earlier commit. The rules in `prompt.py` (and the -m override)
keep the message about what THIS commit actually changes.

`history.py` reads the last 200 commit subjects and bodies and measures the types,
scopes, body shape and language this repo actually uses, so the message written
belongs in this history rather than being generically correct.

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

from .diffing import (  # noqa: E402
    DEMOTE_MIN_CHARS,
    DEMOTED_CLASSES,
    MAX_DIFF_CHARS,
    budget_diff,
    chunk_path,
    count_changes,
    demote_diff,
    split_diff,
    truncate,
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
)
from .history import (  # noqa: E402
    HISTORY_DEPTH,
    MAX_HOUSE_STYLE_CHARS,
    MIN_COMMITS,
    RECORD_SEP,
    body_shape,
    bullet_marker,
    dominant_language,
    house_style,
    parse_commit,
    split_records,
    strip_prefix,
    subject_type_scope,
    trailer_keys,
)
from .gitio import (  # noqa: E402
    MAX_SUMMARY_CHARS,
    get_recent_commits,
    get_staged_diff,
    get_staged_files,
    get_staged_summary,
    get_unstaged_files,
    partially_staged,
    run,
    unstaged_warning,
)
from .prompt import _system_prompt, build_user_prompt  # noqa: E402
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

from .cli import main, prog_name  # noqa: E402  (last: it imports the rest)

__all__ = [
    "__version__",
    "main",
    "prog_name",
    "PROVIDERS",
    "call_model",
    "classify",
    "classify_files",
    "doc_guard_note",
    "house_style",
    "get_recent_commits",
    "budget_diff",
    "demote_diff",
    "get_staged_diff",
    "get_staged_files",
    "get_staged_summary",
    "post_json",
]
