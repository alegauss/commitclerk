#!/bin/sh
# POSIX counterpart of run-commit.cmd: check the API key, stage everything,
# then hand every argument through to commitclerk.py.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "Error: OPENAI_API_KEY is not set." >&2
    exit 2
fi

if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "Error: no python3 or python on PATH." >&2
    exit 2
fi

# -A, not a glob: a glob skips dotfiles and never records deletions.
if ! git add -A; then
    echo "git add failed." >&2
    exit 1
fi

exec "$PYTHON" "$SCRIPT_DIR/commitclerk.py" "$@"
