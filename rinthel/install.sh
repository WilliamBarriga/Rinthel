#!/usr/bin/env bash
# Bootstrap de un solo comando para una máquina nueva: detecta Python
# >=3.13 (venv del daemon) e instala Rust si falta (build del cliente), compila el binario
# release y lanza la TUI vía rinthel-boot.sh. No toca GPU/CUDA/Docker — eso
# vive enteramente en las fases de [0] INSTALL dentro de la propia TUI.
# Idempotente: correrlo de nuevo con todo ya instalado no rompe nada.
#
# Uso:
#   rinthel/install.sh                 bootstrap y abre la TUI
#   rinthel/install.sh --skip-launch   solo el bootstrap
#   rinthel/install.sh --voice         bootstrap, arranca el daemon si hace falta y corre
#                                      INSTALL con la voz local (opt-in, solo Linux,
#                                      repetible sobre una Instance existente); no abre la TUI
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$DIR")"

VOICE=0
ARGS=()
for arg in "$@"; do
    if [[ "$arg" == "--voice" ]]; then VOICE=1; else ARGS+=("$arg"); fi
done
set -- "${ARGS[@]+"${ARGS[@]}"}"
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
    echo "[install] Requiere Python 3.13+. En Ubuntu 26.04: sudo apt install python3 python3-venv" >&2
    echo "[install] Para otro intérprete: PYBIN=/ruta/python rinthel/install.sh" >&2
    exit 1
fi

# rustup may already exist but not be on PATH in this terminal.
if [[ -f "$HOME/.cargo/env" ]]; then
    source "$HOME/.cargo/env"
fi
for tool in curl cc; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "[install] Falta $tool. Ejecuta: sudo apt install build-essential curl ca-certificates" >&2
        exit 1
    fi
done

echo "[install] usando $PYTHON ($("$PYTHON" --version 2>&1))"

if [[ ! -x "$DIR/.venv/bin/python" ]]; then
    "$PYTHON" -m venv "$DIR/.venv" || {
        echo "[install] Instala el paquete venv de tu Python (Ubuntu: sudo apt install python3-venv)." >&2
        exit 1
    }
fi

"$DIR/.venv/bin/python" -m pip install -q -e "$DIR"

# ── Rust (cliente) ──────────────────────────────────────────────
# El binario Rust es el cliente reemplazable, el daemon Python es la
# infraestructura persistente — este script bootstrapea ambos toolchains, el
# arranque real (autostart + pidfile) queda en rinthel-boot.sh.
if ! command -v cargo >/dev/null 2>&1; then
    echo "[install] no encontré cargo — instalando Rust vía rustup (no interactivo)..." >&2
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    # rustup deja esto en ~/.bashrc para shells nuevas; esta sigue corriendo
    # el script, así que lo sourceamos acá para que el cargo build de abajo
    # lo encuentre sin reabrir terminal.
    # shellcheck disable=SC1091
    source "$HOME/.cargo/env"
fi

echo "[install] usando $(cargo --version)"
(cd "$DIR/rinthel-client" && cargo build --release --locked)

# INSTALL --voice lo corre el daemon (POST /install, bajo el lock global del
# lifecycle): primero el daemon arriba, después el pedido; su resultado es el
# del script.
if (( VOICE )); then
    "$DIR/rinthel-boot.sh" --daemon-only
    exec "$DIR/.venv/bin/python" -m rinthel_tui.install --root "$ROOT" --voice
fi

if [[ "${1:-}" == "--skip-launch" ]]; then
    exit 0
fi
exec "$DIR/rinthel-boot.sh" "$@"
