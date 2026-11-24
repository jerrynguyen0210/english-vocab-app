#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../backend" && pwd)
cd -- "$BACKEND_DIR"
if [[ -x .venv/bin/python ]]; then
    exec .venv/bin/python -m app.manage_common_words "$@"
fi
exec python3 -m app.manage_common_words "$@"
