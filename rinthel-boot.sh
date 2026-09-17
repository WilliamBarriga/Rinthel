#!/usr/bin/env bash
# Autostart del daemon (con pidfile) + lanza el cliente Rust. Sesión 11 del
# port-map (.scratch/ratatui-migration/port-issues/11-hardening-pidfile-autostart.md):
# el daemon es infraestructura persistente e independiente del cliente (ver
# issues/04-packaging-entrypoint.md) — sobrevive a que cierres la TUI, hasta
# que corras `--stop` o apagues la máquina.
#
# Ejecutar SIEMPRE desde (o con cwd dentro de) la raíz del repo: DIR se
# resuelve relativo a este script. Config vía .env, ver README/.env.example.
#
# Uso:
#   ./rinthel-boot.sh          arranca el daemon si hace falta, abre el cliente
#   ./rinthel-boot.sh --stop   apaga el daemon (sin abrir el cliente)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$DIR/.venv/bin/python"
BINARY="$DIR/rinthel-client/target/release/rinthel"
PIDFILE="$DIR/.rinthel-daemon.pid"
ENV_FILE="$DIR/.env"
DAEMON_LOG="$DIR/logs/daemon.log"
READY_TIMEOUT=10 # segundos de poll tras autostart antes de rendirse (sesión 11, grillado con Tarkark)

port_from_env() {
    local value="8765"
    if [[ -f "$ENV_FILE" ]]; then
        local line
        line="$(grep -E '^RINTHEL_DAEMON_PORT=' "$ENV_FILE" | tail -n1 || true)"
        [[ -n "$line" ]] && value="${line#RINTHEL_DAEMON_PORT=}"
    fi
    echo "$value"
}

port_in_use() {
    (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

pid_alive() {
    kill -0 "$1" 2>/dev/null
}

# PID guardado en el pidfile si sigue vivo, o "" si no hay pidfile o quedó
# stale (proceso muerto sin limpiar — la norma en una máquina que se
# reinicia, no la excepción: se trata como "no corriendo", sin quejarse).
running_pid() {
    if [[ -f "$PIDFILE" ]]; then
        local pid
        pid="$(cat "$PIDFILE")"
        if [[ -n "$pid" ]] && pid_alive "$pid"; then
            echo "$pid"
            return
        fi
        rm -f "$PIDFILE"
    fi
    echo ""
}

stop_daemon() {
    local pid
    pid="$(running_pid)"
    if [[ -z "$pid" ]]; then
        echo "[boot] el daemon no está corriendo (o no fue lanzado por este script — sin pidfile)."
        return
    fi
    echo "[boot] apagando daemon (PID $pid)..."
    kill -TERM "$pid"
    for _ in $(seq 1 20); do
        pid_alive "$pid" || break
        sleep 0.25
    done
    if pid_alive "$pid"; then
        echo "[boot] error: el daemon (PID $pid) no terminó a tiempo tras SIGTERM." >&2
        exit 1
    fi
    rm -f "$PIDFILE"
    echo "[boot] daemon apagado."
}

if [[ "${1:-}" == "--stop" ]]; then
    stop_daemon
    exit 0
fi

if [[ ! -x "$PYTHON" ]]; then
    echo "error: no se encontró $PYTHON — corré ./install.sh primero." >&2
    exit 1
fi
if [[ ! -x "$BINARY" ]]; then
    echo "error: no se encontró $BINARY — corré ./install.sh, o 'cargo build --release' dentro de rinthel-client/." >&2
    exit 1
fi

PORT="$(port_from_env)"
pid="$(running_pid)"

if [[ -n "$pid" ]]; then
    echo "[boot] daemon ya corriendo (PID $pid, puerto $PORT)."
elif port_in_use "$PORT"; then
    # Algo escucha ahí sin que este script lo haya lanzado (arrancado a
    # mano, u otro daemon) — lo dejamos en paz, sin pidfile propio.
    echo "[boot] puerto $PORT ya en uso (proceso ajeno a este script) — asumiendo que es el daemon."
else
    echo "[boot] daemon no está corriendo — autostarteando en puerto $PORT..."
    mkdir -p "$(dirname "$DAEMON_LOG")"
    RINTHEL_DAEMON_PORT="$PORT" nohup "$PYTHON" -m rinthel_tui.daemon >>"$DAEMON_LOG" 2>&1 &
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

exec "$BINARY" --port "$PORT" "$@"
