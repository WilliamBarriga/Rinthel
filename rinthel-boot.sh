#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$DIR/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    echo "error: no se encontró $PYTHON — crea el venv primero:" >&2
    echo "  python3 -m venv \"$DIR/.venv\" && \"$PYTHON\" -m pip install -e \"$DIR\"" >&2
    exit 1
fi
exec "$PYTHON" -m rinthel_tui "$@"
