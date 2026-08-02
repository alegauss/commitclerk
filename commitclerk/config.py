"""The two config files, and the one ladder every setting is resolved through.

CLI > environment > `./.clerk.json` > `~/.config/clerk/config.json` > built-in
default. That order is written once, in `layered()`, because a precedence rule
restated per setting is a precedence rule that drifts per setting.

JSON and not TOML: `tomllib` landed in 3.11, the floor here is 3.8, and a parser
of our own would cost the zero-dependency rule. Standard library only.
"""

from __future__ import annotations

import json
import os

PROJECT_CONFIG = ".clerk.json"
# under the user's `~/.config`, which is where the second half of the path lives.
USER_CONFIG = ("clerk", "config.json")

# name -> the type the value must have. A key absent from this table is a key
# this version does not know: it is reported and ignored, so a config written
# for a later release does not stop an earlier one from committing.
SETTINGS = {
    "provider": str,
    "model": str,
    "base_url": str,
    "timeout": int,
    "max_chars": int,
    "house_style": bool,
}

_TYPE_NAMES = {str: "a string", int: "a whole number", bool: "true or false"}


class ConfigError(Exception):
    """A file the user wrote that cannot be honoured exactly as written."""


def user_config_path(home: str | None = None) -> str:
    return os.path.join(home if home is not None else os.path.expanduser("~"),
                        ".config", *USER_CONFIG)


def project_config_path(root: str | None) -> str | None:
    """`<repo root>/.clerk.json`, or None outside a repository.

    The root, not the working directory: which subdirectory you happen to be
    standing in must not change what the tool does. Normalised because git
    reports the root with forward slashes even on Windows, and the path is shown
    to the user in every message about this file.
    """
    return os.path.normpath(os.path.join(root, PROJECT_CONFIG)) if root else None


def env_value(name: str | None) -> str | None:
    """An environment variable, or None when it is unset *or* empty.

    An exported-but-empty variable is how a shell says "not set". Letting "" win
    the ladder would call the API with an empty model name.
    """
    return (os.environ.get(name) if name else None) or None


def read_config(path: str | None) -> tuple[dict, list[str]]:
    """(values, notices) for `path`, or ({}, []) when there is no such file.

    Raises ConfigError for a file that exists and cannot be honoured. A syntax
    error or a wrongly typed value is not something to route around: the user
    wrote the file to change the tool's behaviour, and quietly doing something
    else is the failure this project exists to avoid.
    """
    if not path or not os.path.isfile(path):
        return {}, []
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    # ValueError covers both JSONDecodeError and the UnicodeDecodeError a file
    # that is not really UTF-8 raises on read.
    except (OSError, ValueError) as exc:
        raise ConfigError("cannot read {}: {}".format(path, exc))
    if not isinstance(data, dict):
        raise ConfigError("{} must contain a JSON object".format(path))

    values: dict = {}
    notices: list[str] = []
    for key in sorted(data):
        expected = SETTINGS.get(key)
        if expected is None:
            notices.append("Note: unknown setting '{}' in {}, ignored.".format(key, path))
            continue
        value = data[key]
        # `bool` is a subclass of `int` in Python, so an int setting has to turn
        # `true` away by hand or `"timeout": true` would mean a one-second timeout.
        if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            raise ConfigError("{}: '{}' must be {}".format(path, key, _TYPE_NAMES[expected]))
        values[key] = value
    return values, notices


def load_config(root: str | None, home: str | None = None) -> tuple[dict, dict, list[str]]:
    """(project, user, notices) - both files, read and kept apart.

    Unmerged on purpose: the ladder puts the environment above one of them and
    nothing above the other, so merging here would be a second precedence rule.
    """
    project, project_notices = read_config(project_config_path(root))
    user, user_notices = read_config(user_config_path(home))
    return project, user, project_notices + user_notices


def layered(cli, env, project, user, default):
    """CLI > environment > project file > user file > built-in default.

    The only place that order exists. Every setting hands over its five
    candidates in it, so a new setting cannot quietly invent a different one.
    `None` alone means "not set at this layer" - a `false` or `0` written on
    purpose is honoured, which is why this is not a chain of `or`.
    """
    for value in (cli, env, project, user, default):
        if value is not None:
            return value
    return None
