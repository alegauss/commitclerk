"""One table of provider adapters, and the single network call.

Four slots differ between vendors: url, headers, payload, extract. Everything
else -- retry, parameter repair, error text -- is shared.
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request

from .config import env_value, layered
from .prompt import _system_prompt, build_user_prompt

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"
DEFAULT_OLLAMA_MODEL = "qwen2.5-coder"
DEFAULT_PROVIDER = "openai"
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


def resolve_model(
    spec: dict,
    cli_model: str | None = None,
    project: str | None = None,
    user: str | None = None,
) -> str:
    """Model to call, through the one ladder in `config.py`.

    The provider's own env var is this setting's environment layer: `OPENAI_MODEL`
    for openai, `ANTHROPIC_MODEL` for anthropic.
    """
    return layered(
        cli_model or None,
        env_value(spec.get("model_env")),
        project,
        user,
        spec["default_model"],
    )


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


def resolve_base(
    spec: dict,
    cli_base: str | None = None,
    project: str | None = None,
    user: str | None = None,
) -> str:
    """Base URL to call, through the one ladder in `config.py`.

    Most vendors clone the OpenAI wire format, so pointing this at Ollama,
    LM Studio, vLLM, OpenRouter, Groq, Together or Azure needs no new adapter.
    """
    return layered(
        cli_base or None,
        env_value(spec.get("base_env")),
        project,
        user,
        spec["default_base"],
    )


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


def complete(
    spec: dict,
    api_key: str | None,
    model: str,
    system: str,
    user: str,
    *,
    base: str | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> str:
    """One request: build the payload, post it, return the text.

    Split out from `call_model` because `--deep` makes a second kind of call --
    a per-file summary — and a second copy of the payload/headers/extract dance
    is a second place for a provider quirk to be fixed only once.
    """
    payload = spec["payload"](model, system, user)
    headers = {"Content-Type": "application/json"}
    headers.update(spec["headers"](api_key))
    data = post_json(
        provider_url(spec, base),
        payload,
        headers,
        label=spec["label"],
        timeout=timeout,
    )
    return spec["extract"](data).strip()


def call_model(
    spec: dict,
    api_key: str | None,
    model: str,
    diff: str,
    files: list[str],
    *,
    context: dict | None = None,
    base: str | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> str:
    # One bag rather than one parameter per prompt section: every context source the
    # tool grows (guard, summary, classes, house style, examples, scope, ...) would
    # otherwise widen this signature and every call site along with it. The keys are
    # `build_user_prompt`'s keyword arguments, which is the only contract there is.
    context = context or {}
    label = spec["label"]
    text = complete(
        spec,
        api_key,
        model,
        _system_prompt(body_only=context.get("title") is not None),
        build_user_prompt(diff, files, **context),
        base=base,
        timeout=timeout,
    )
    if not text:
        # Better to fail than to hand `git commit` an empty message. The usual
        # cause is a reasoning model that spent the whole output budget before
        # writing any prose.
        raise SystemExit(
            f"{label} returned no message text (model: {model}). "
            "Try a smaller diff, or a model that does not reason before answering."
        )
    return text
