#!/usr/bin/env bash
# Lanza RinthelApp (rinthel_tui) usando el venv de dev de este repo.
# Ejecutar SIEMPRE desde (o con cwd dentro de) la raíz del repo: DIR se
# resuelve relativo a este script, pero .venv se busca ahí mismo — no
# funciona symlinkeado/copiado a otro lugar. Config vía .env, ver README.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$DIR/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    echo "error: no se encontró $PYTHON — crea el venv primero:" >&2
    echo "  python3 -m venv \"$DIR/.venv\" && \"$PYTHON\" -m pip install -e \"$DIR\"" >&2
    echo "  (o corré ./install.sh, que hace esto mismo en una máquina nueva)" >&2
    exit 1
fi
exec "$PYTHON" -m rinthel_tui "$@"
