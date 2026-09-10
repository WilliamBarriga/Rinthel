#!/usr/bin/env bash
# whisper-server no tiene auth propia (código fuente lo confirma: cero
# flags, Access-Control-Allow-Origin:* hardcodeado) — corre en un puerto
# interno del contenedor, no publicado, y solo proxy.py (que sí valida
# token/origin) escucha en el puerto que docker-compose publica al host.
set -euo pipefail

whisper-server \
    --host 127.0.0.1 --port 9091 \
    -m /app/models/ggml-base.bin \
    -t "$(nproc)" \
    -l "${WHISPER_LANGUAGE:-auto}" \
    --convert \
    --tmp-dir /tmp &
WHISPER_PID=$!

python3 /app/proxy.py \
    --host 0.0.0.0 --port 8090 \
    --upstream-host 127.0.0.1 --upstream-port 9091 &
PROXY_PID=$!

# Si cualquiera de los dos muere, el contenedor sale distinto de 0 y
# `restart: unless-stopped` en compose lo vuelve a levantar — evita un
# proxy zombie devolviendo 502 para siempre si whisper-server crashea.
wait -n "$WHISPER_PID" "$PROXY_PID"
exit $?
