#!/usr/bin/env bash
# Bootstrap de un solo comando para una máquina nueva: detecta/instala Python
# >=3.13, crea el venv de este repo y lanza la TUI. No toca GPU/CUDA/Docker —
# eso vive enteramente en las fases de [0] INSTALL dentro de la propia TUI.
# Idempotente: correrlo de nuevo con todo ya instalado no rompe nada.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIN_MINOR=13

_version_ok() {
    local bin="$1"
    command -v "$bin" >/dev/null 2>&1 || return 1
    "$bin" -c "import sys; sys.exit(0 if (sys.version_info[0], sys.version_info[1]) >= (3, $MIN_MINOR) else 1)" 2>/dev/null
}

find_python() {
    for candidate in python3.13 python3.14 python3.15 python3; do
        if _version_ok "$candidate"; then
            command -v "$candidate"
            return 0
        fi
    done
    return 1
}

if [[ -n "${PYBIN:-}" ]]; then
    if ! _version_ok "$PYBIN"; then
        echo "[install] error: PYBIN=$PYBIN no existe o no es Python >=3.${MIN_MINOR}" >&2
        exit 1
    fi
    PYTHON="$PYBIN"
else
    PYTHON="$(find_python || true)"
fi

if [[ -z "${PYTHON:-}" ]]; then
    echo "[install] No encontré Python >=3.${MIN_MINOR} en PATH — instalando vía PPA deadsnakes..." >&2
    if ! command -v sudo >/dev/null 2>&1; then
        echo "[install] error: hace falta sudo para instalar Python. Instalá Python 3.${MIN_MINOR}+ a mano (pyenv, o PYBIN=/ruta/a/python3.13 ./install.sh)." >&2
        exit 1
    fi
    sudo apt-get update
    sudo apt-get install -y software-properties-common
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt-get update
    if sudo apt-get install -y python3.13 python3.13-venv; then
        PYTHON="$(command -v python3.13)"
    else
        echo "[install] error: no pude instalar python3.13 vía deadsnakes." >&2
        echo "  Alternativas: instalá Python 3.${MIN_MINOR}+ con pyenv, o corré:" >&2
        echo "    PYBIN=/ruta/a/tu/python3.13 ./install.sh" >&2
        exit 1
    fi
fi

echo "[install] usando $PYTHON ($("$PYTHON" --version 2>&1))"

if [[ ! -x "$DIR/.venv/bin/python" ]]; then
    "$PYTHON" -m venv "$DIR/.venv"
fi

"$DIR/.venv/bin/pip" install -q -e "$DIR"

exec "$DIR/.venv/bin/python" -m rinthel_tui "$@"
