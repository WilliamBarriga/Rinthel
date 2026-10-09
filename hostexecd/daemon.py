"""Daemon FastAPI de hostexecd — ejecuta comandos de shell en el host real
desde una tool de pi (``host_exec``) que corre dentro del contenedor
Pithagoras. Ver ``plans/rinthel-host-exec.md`` para el diseño completo
(grillado con Tarkark, todas las decisiones cerradas ahí, no repetidas acá).

Corré con:  .venv/bin/python -m hostexecd.daemon

Deliberadamente separado de ``rinthel_tui.daemon`` (que administra el
lifecycle del propio stack de Rinthel: llama-server/Understory/Pithagoras):
este daemon no sabe nada de esos servicios, solo corre lo que se le pida
como el usuario que lo lanzó (``tarkark``, sin sudo, sin escalar
privilegios) y audita cada ejecución en ``logs/hostexecd.log``. Blast
radius aislado a propósito — ver decisión de diseño 4 del plan.

Bloqueante, sin streaming ni gestión de procesos de fondo: mismo patrón
REST-bloqueante que ``docs/adr/0001-daemon-protocol-shape.md`` documenta
para ``rinthel_tui.daemon`` (``POST`` que espera el resultado completo y lo
devuelve, en vez de progreso incremental).

Endpoints:

- ``POST /exec``: corre un comando (``executor.run_command`` —
  ``subprocess.run(shell=True)``, sin privilegios elevados), con timeout, y
  devuelve ``exit_code``/``stdout``/``stderr``/``duration_ms``/
  ``timed_out``. Requiere el header ``X-Rinthel-Token`` (ver ``auth.py``) —
  sin match, ``401``. Cada llamada se audita (``audit.py``) antes de
  devolver la respuesta.
- ``GET /history``: últimas ``limit`` entradas del audit log (default 20),
  también requiere el token.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from hostexecd import audit, auth, executor

# hostexecd/daemon.py -> repo root (mismo criterio que rinthel_tui/daemon.py).
# Sin esto, RINTHEL_HOSTEXECD_TOKEN nunca llega al proceso: `rinthel-boot.sh`
# solo pasa el puerto explícito al lanzar `nohup ... hostexecd.daemon`, no el
# resto de `.env` — sin este load_dotenv, auth.expected_token() da siempre
# None y toda request devuelve 401, sin importar qué token mande el cliente.
_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")

app = FastAPI()

MAX_HISTORY = 200


def _require_token(token: str | None) -> None:
    if not auth.check_token(token):
        raise HTTPException(status_code=401, detail="invalid or missing token")


@app.post("/exec")
def exec_command(
    payload: dict, x_rinthel_token: str | None = Header(default=None, alias=auth.TOKEN_HEADER)
) -> JSONResponse:
    _require_token(x_rinthel_token)

    command = payload.get("command")
    if not isinstance(command, str) or not command.strip():
        raise HTTPException(status_code=400, detail="'command' must be a non-empty string")
    cwd = payload.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        raise HTTPException(status_code=400, detail="'cwd' must be a string or null")
    # Chequeado acá y no dejado a subprocess: su FileNotFoundError salía como
    # un 500 sin auditar, y el modelo no se enteraba de qué había pedido mal.
    if cwd is not None and not Path(cwd).is_dir():
        raise HTTPException(status_code=400, detail=f"'cwd' is not a directory on the host: {cwd}")
    timeout = payload.get("timeout")
    # bool es subclase de int en Python: sin excluirlo, `true` pasaba como 1s.
    if timeout is not None and (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not 1 <= timeout <= executor.MAX_TIMEOUT
    ):
        raise HTTPException(
            status_code=400,
            detail=f"'timeout' must be a number of seconds from 1 to {executor.MAX_TIMEOUT}, or null",
        )

    result = executor.run_command(command, cwd, int(timeout) if timeout else None)

    audit.record(
        command=command,
        cwd=cwd,
        exit_code=result.exit_code,
        duration_ms=result.duration_ms,
        stdout_len=result.stdout_bytes,
        stderr_len=result.stderr_bytes,
        timed_out=result.timed_out,
    )

    return JSONResponse(
        {
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
            "timed_out": result.timed_out,
        }
    )


@app.get("/history")
def history(
    limit: int = 20, x_rinthel_token: str | None = Header(default=None, alias=auth.TOKEN_HEADER)
) -> JSONResponse:
    _require_token(x_rinthel_token)
    # limit=0 devolvía el log entero (`lines[-0:]` es la lista completa).
    if not 1 <= limit <= MAX_HISTORY:
        raise HTTPException(status_code=400, detail=f"'limit' must be from 1 to {MAX_HISTORY}")
    return JSONResponse({"entries": audit.read_recent(limit)})


def main() -> None:
    import uvicorn

    # Puerto propio de este daemon (distinto de rinthel_tui.daemon) —
    # overrideable por `.env`; `rinthel-boot.sh` lo lee de ahí para
    # chequear si ya está arriba antes de autostartearlo. Default 8766:
    # siguiente libre tras 8765 (rinthel_tui)/3800 (Understory)/4100
    # (Pithagoras).
    port = int(os.getenv("RINTHEL_HOSTEXECD_PORT", "8766"))
    print(f"[hostexecd] {time.strftime('%H:%M:%S')} arrancando en http://127.0.0.1:{port}")
    if auth.expected_token() is None:
        print(
            "[hostexecd] AVISO: RINTHEL_HOSTEXECD_TOKEN no está seteado — "
            "todas las requests van a devolver 401 hasta que se configure."
        )
    # workers=1, mismo criterio que rinthel_tui/daemon.py::main(): un solo
    # proceso real por pidfile, sin necesidad de coordinar estado entre
    # workers (acá no hay nada mutable en memoria para empezar).
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", workers=1)


if __name__ == "__main__":
    main()
