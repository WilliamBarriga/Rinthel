#!/usr/bin/env bash
# Autostart del daemon (con pidfile) + lanza el cliente Rust. El daemon es
# infraestructura persistente e independiente del cliente — sobrevive a que
# cierres la TUI, hasta que corras `--stop` o apagues la máquina.
#
# DIR (este script, rinthel/) es el cwd; ROOT (raíz de la Instance, su padre)
# guarda .env, logs/ y los pidfiles.
# Config vía .env, ver README/.env.example.
#
# Uso:
#   ./rinthel-boot.sh          arranca el daemon si hace falta, abre el cliente
#   ./rinthel-boot.sh --stop   apaga el daemon (sin abrir el cliente)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$DIR")"
cd "$DIR"
if [[ -f "$HOME/.cargo/env" ]]; then source "$HOME/.cargo/env"; fi
PYTHON="$DIR/.venv/bin/python"
CARGO_MANIFEST="$DIR/rinthel-client/Cargo.toml"
BINARY="$DIR/rinthel-client/target/release/rinthel"
PIDFILE="$ROOT/.rinthel-daemon.pid"
ENV_FILE="$ROOT/.env"
DAEMON_LOG="$ROOT/logs/daemon.log"
# hostexecd: daemon separado que ejecuta comandos de shell en el host real
# (ver plans/rinthel-host-exec.md) — mismo patrón de pidfile/autostart que
# el daemon de arriba, en paralelo, sin pisar nada de lo suyo.
HOSTEXECD_PIDFILE="$ROOT/.rinthel-hostexecd.pid"
# stdout/stderr del proceso — NO logs/hostexecd.log, que es el audit log
# JSONL de hostexecd/audit.py: mezclarlos llenaba la auditoría de tracebacks.
HOSTEXECD_LOG="$ROOT/logs/hostexecd.out.log"
READY_TIMEOUT=10 # segundos de poll tras autostart antes de rendirse

# `cargo build` es incremental — sin cambios desde el último boot, esto es
# casi gratis (chequeo de mtimes, nada que recompilar). Se corre en cada
# arranque para que el binario nunca quede desactualizado respecto al
# código fuente, sin depender de que alguien se acuerde de correr
# `cargo build --release` a mano después de un `git pull`.
build_client() {
    if ! command -v cargo >/dev/null 2>&1; then
        if [[ -x "$BINARY" ]]; then
            echo "[boot] cargo no está en PATH — sigo con el binario existente sin reconstruir." >&2
            return
        fi
        echo "error: no se encontró cargo y no hay binario previo en $BINARY — instalá Rust (rustup.rs) o corré rinthel/install.sh." >&2
        exit 1
    fi
    echo "[boot] compilando cliente Rust (cargo build --release)..."
    if ! cargo build --release --locked --manifest-path "$CARGO_MANIFEST"; then
        if [[ -x "$BINARY" ]]; then
            echo "[boot] la compilación falló — sigo con el binario previo ($BINARY), puede estar desactualizado." >&2
        else
            echo "error: la compilación falló y no hay binario previo en $BINARY." >&2
            exit 1
        fi
    fi
}

# Generalizada sobre la var de entorno y el default (antes hardcodeaba
# RINTHEL_DAEMON_PORT/8765) para que hostexecd pueda reusarla en vez de
# duplicar la lógica de parseo del .env.
port_from_env() {
    local var_name="$1" default_value="$2"
    VAR_NAME="$var_name" DEFAULT_VALUE="$default_value" ENV_FILE="$ENV_FILE" "$PYTHON" -c 'import os; from dotenv import load_dotenv; load_dotenv(os.environ["ENV_FILE"]); p=int(os.environ.get(os.environ["VAR_NAME"], os.environ["DEFAULT_VALUE"])); assert 1 <= p <= 65535; print(p)'
}

port_in_use() {
    (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

pid_alive() {
    kill -0 "$1" 2>/dev/null
}

# PID guardado en el pidfile dado si sigue vivo, o "" si no hay pidfile o
# quedó stale (proceso muerto sin limpiar — la norma en una máquina que se
# reinicia, no la excepción: se trata como "no corriendo", sin quejarse).
# Generalizada sobre el pidfile (antes hardcodeaba $PIDFILE) para que
# hostexecd la reuse en vez de duplicarla.
running_pid() {
    local pidfile="$1"
    if [[ -f "$pidfile" ]]; then
        local pid
        pid="$(cat "$pidfile")"
        if [[ -n "$pid" ]] && pid_alive "$pid"; then
            echo "$pid"
            return
        fi
        rm -f "$pidfile"
    fi
    echo ""
}

# $1: pidfile, $2: nombre para los mensajes ("daemon"/"hostexecd").
stop_daemon() {
    local pidfile="$1" label="$2" pid
    pid="$(running_pid "$pidfile")"
    if [[ -z "$pid" ]]; then
        echo "[boot] $label no está corriendo (o no fue lanzado por este script — sin pidfile)."
        return
    fi
    echo "[boot] apagando $label (PID $pid)..."
    kill -TERM "$pid"
    for _ in $(seq 1 20); do
        pid_alive "$pid" || break
        sleep 0.25
    done
    if pid_alive "$pid"; then
        echo "[boot] error: $label (PID $pid) no terminó a tiempo tras SIGTERM." >&2
        exit 1
    fi
    rm -f "$pidfile"
    echo "[boot] $label apagado."
}

if [[ "${1:-}" == "--stop" ]]; then
    stop_daemon "$PIDFILE" "daemon"
    stop_daemon "$HOSTEXECD_PIDFILE" "hostexecd"
    exit 0
fi

if [[ ! -x "$PYTHON" ]]; then
    echo "error: no se encontró $PYTHON — corré rinthel/install.sh primero." >&2
    exit 1
fi
build_client

# Provision before either daemon reads .env; reruns preserve existing secrets.
"$PYTHON" -m rinthel_tui.install.host_exec "$ROOT"

# Mismo secreto que valida la access policy `service` del daemon: la TUI lo
# manda en cada request (`X-Rinthel-Service-Secret`). Se genera acá si falta,
# antes de arrancar el daemon — sin él ni `POST /install` pasaría en una
# Instance nueva. `ensure-secret` es idempotente y deja el `.env` en 600.
"$PYTHON" -m rinthel_tui.instance --root "$ROOT" ensure-secret RINTHEL_SERVICE_SECRET
SERVICE_SECRET="$("$PYTHON" -m rinthel_tui.instance --root "$ROOT" get RINTHEL_SERVICE_SECRET)"

PORT="$(port_from_env RINTHEL_DAEMON_PORT 8765)"
pid="$(running_pid "$PIDFILE")"

if [[ -n "$pid" ]]; then
    echo "[boot] daemon ya corriendo (PID $pid, puerto $PORT)."
elif port_in_use "$PORT"; then
    # Algo escucha ahí sin que este script lo haya lanzado (arrancado a
    # mano, u otro daemon) — lo dejamos en paz, sin pidfile propio.
    echo "[boot] puerto $PORT ya en uso (proceso ajeno a este script) — asumiendo que es el daemon."
else
    echo "[boot] daemon no está corriendo — autostarteando en puerto $PORT..."
    mkdir -p "$(dirname "$DAEMON_LOG")"
    RINTHEL_DAEMON_PORT="$PORT" PYTHONUNBUFFERED=1 nohup "$PYTHON" -m rinthel_tui.daemon >>"$DAEMON_LOG" 2>&1 &
    echo $! >"$PIDFILE"
    disown
    tries=0
    max_tries=$((READY_TIMEOUT * 2)) # poll cada 0.5s
    until port_in_use "$PORT"; do
        if (( tries >= max_tries )); then
            echo "[boot] error: el daemon no respondió en :$PORT tras ${READY_TIMEOUT}s — revisá $DAEMON_LOG." >&2
            exit 1
        fi
        sleep 0.5
        tries=$((tries + 1))
    done
    echo "[boot] daemon arriba (PID $(cat "$PIDFILE"))."
fi

# hostexecd — mismo patrón exacto que el bloque de arriba, en paralelo. Sin
# cliente propio (no lo usa el binario Rust), solo necesita estar arriba
# antes de que Rinthel intente llamar a la tool host_exec.
HOSTEXECD_PORT="$(port_from_env RINTHEL_HOSTEXECD_PORT 8766)"
hostexecd_pid="$(running_pid "$HOSTEXECD_PIDFILE")"

if [[ -n "$hostexecd_pid" ]]; then
    echo "[boot] hostexecd ya corriendo (PID $hostexecd_pid, puerto $HOSTEXECD_PORT)."
elif port_in_use "$HOSTEXECD_PORT"; then
    echo "[boot] puerto $HOSTEXECD_PORT ya en uso (proceso ajeno a este script) — asumiendo que es hostexecd."
else
    echo "[boot] hostexecd no está corriendo — autostarteando en puerto $HOSTEXECD_PORT..."
    mkdir -p "$(dirname "$HOSTEXECD_LOG")"
    RINTHEL_HOSTEXECD_PORT="$HOSTEXECD_PORT" nohup "$PYTHON" -m hostexecd.daemon >>"$HOSTEXECD_LOG" 2>&1 &
    echo $! >"$HOSTEXECD_PIDFILE"
    disown
    tries=0
    max_tries=$((READY_TIMEOUT * 2)) # poll cada 0.5s
    until port_in_use "$HOSTEXECD_PORT"; do
        if (( tries >= max_tries )); then
            echo "[boot] error: hostexecd no respondió en :$HOSTEXECD_PORT tras ${READY_TIMEOUT}s — revisá $HOSTEXECD_LOG." >&2
            exit 1
        fi
        sleep 0.5
        tries=$((tries + 1))
    done
    echo "[boot] hostexecd arriba (PID $(cat "$HOSTEXECD_PIDFILE"))."
fi

RINTHEL_SERVICE_SECRET="$SERVICE_SECRET" exec "$BINARY" --port "$PORT" "$@"
