#!/usr/bin/env bash
# Reaplica, en cada boot, lo que "docker compose up" de understory-poc no
# puede resolver solo: Understory corre en su propio bridge (understory_net,
# interfaz fija br-understory — ver networks.default en
# ~/understory-poc/docker-compose.yml), pero el alias host.docker.internal
# que usa para llegar a llama-server SIEMPRE resuelve a 172.17.0.1 (el
# gateway del bridge default de Docker), sin importar en qué red esté el
# container. Y llama-server solo escucha en 127.0.0.1:8080 (ver
# rinthel_tui/lifecycle/services.py::_llama_argv — no pasa --host). Sin este
# NAT, Understory tira "Connect Timeout Error" contra host.docker.internal:8080
# apenas intenta hacer una query real (memory_query).
#
# Idempotente — seguro de correr en cada boot o a mano.
set -euo pipefail

IFACE=br-understory
GATEWAY_TARGET=172.17.0.1
LLAMA_PORT=8080

for i in $(seq 1 30); do
    ip link show "$IFACE" >/dev/null 2>&1 && break
    sleep 2
done
if ! ip link show "$IFACE" >/dev/null 2>&1; then
    echo "understory-net-fix: $IFACE no apareció tras 60s — ¿understory-poc está levantado?" >&2
    exit 1
fi

# conf.default.route_localnet=1 hace que CUALQUIER interfaz que Docker cree
# después (incluida br-understory si se recrea) herede route_localnet — así
# no dependemos de que exista antes de que corra este script.
sysctl -w net.ipv4.conf.default.route_localnet=1 >/dev/null
sysctl -w "net.ipv4.conf.${IFACE}.route_localnet=1" >/dev/null

if ! iptables -t nat -C PREROUTING -i "$IFACE" -p tcp -d "$GATEWAY_TARGET" \
        --dport "$LLAMA_PORT" -j DNAT --to-destination "127.0.0.1:${LLAMA_PORT}" 2>/dev/null; then
    iptables -t nat -A PREROUTING -i "$IFACE" -p tcp -d "$GATEWAY_TARGET" \
        --dport "$LLAMA_PORT" -j DNAT --to-destination "127.0.0.1:${LLAMA_PORT}"
fi

# La regla ufw (allow in on br-understory to 127.0.0.1 port 8080 proto tcp)
# ya vive en /etc/ufw/user.rules y no hace falta reaplicarla acá.

echo "understory-net-fix: OK ($IFACE -> $GATEWAY_TARGET:$LLAMA_PORT -> 127.0.0.1:$LLAMA_PORT)"
