#!/usr/bin/env python3
"""Doble de servicio para el smoke E2E de sesión 04 (hardening real de
boot/terminate) — NO es llama-server/Understory/Pithagoras real.

`e2e_smoke.rs` apunta `RINTHEL_LLAMA_BIN` acá para que `phase_spawn` lance
ESTE script en vez del binario real de llama-server, y apunta
`RINTHEL_UNDERSTORY_PORT`/`RINTHEL_PITHAGORAS_PORT` a los mismos puertos que
este script sirve — así `phase_wait_ready` (compartido entre
LocalProcessService y DockerComposeService) encuentra algo respondiendo 200
sin que ningún docker/llama-server real se toque. `RINTHEL_UNDERSTORY_DIR`/
`RINTHEL_PITHAGORAS_DIR` apuntan a un directorio inexistente, así que
`phase_up`/`phase_down` ni siquiera intentan `docker compose` (ver el guard
"no encontrado — omitido" en managed_service.py).

Ignora argv por completo (recibe los flags reales de llama-server, que no
entiende) — los puertos a servir salen solo de la env var
`RINTHEL_E2E_FAKE_PORTS` (coma-separado).
"""

import http.server
import os
import sys
import threading


class _OkHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args) -> None:
        pass  # silencio — esto no es tráfico real que valga la pena loguear


def main() -> None:
    raw = os.environ.get("RINTHEL_E2E_FAKE_PORTS", "")
    ports = [int(p) for p in raw.split(",") if p.strip()]
    if not ports:
        print("fake_ready_server: RINTHEL_E2E_FAKE_PORTS vacío", file=sys.stderr)
        sys.exit(1)
    servers = [http.server.ThreadingHTTPServer(("127.0.0.1", p), _OkHandler) for p in ports]
    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    servers[0].serve_forever()  # el hilo principal sirve el último — mantiene el proceso vivo


if __name__ == "__main__":
    main()
