"""The FastAPI app of ``hostexecd``: runs shell commands on the host for the
``rinthel_host_exec`` tools of an admin's Session in Deck. See
``docs/07-host-exec.md``.

The daemon starts it as a managed service (``HOSTEXECD_SERVICE``) with
``python -m hostexecd.daemon`` and hands it, by environment, its port
(``RINTHEL_HOSTEXECD_PORT``), its token (``RINTHEL_HOSTEXECD_TOKEN``) and the
Instance root (``RINTHEL_INSTANCE_ROOT``). It reads no ``.env`` of its own.

It knows nothing of the Instance's other services: it runs what it is asked,
as the user that started it, and audits each run. Blocking, without streaming
or background process management, like the daemon's own REST shape.

Endpoints:

- ``POST /exec``: runs a command with a timeout and answers ``exit_code``,
  ``stdout``, ``stderr``, ``duration_ms`` and ``timed_out``. Requires the
  ``X-Rinthel-Token`` header (``401`` otherwise). Audited before answering.
- ``GET /history``: the last ``limit`` audit entries (20 by default), with the
  token too.
- ``GET /health``: the readiness check of the daemon and the Monitor, without
  a token; it says nothing but that the process answers.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from hostexecd import audit, auth, executor

# No schema or docs pages: nothing here is for browsing.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

MAX_HISTORY = 200


def _require_token(token: str | None) -> None:
    if not auth.check_token(token):
        raise HTTPException(status_code=401, detail="invalid or missing token")


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"ok": True})


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
    # Checked here rather than left to subprocess, whose FileNotFoundError
    # would be an unaudited 500 that tells the model nothing.
    if cwd is not None and not Path(cwd).is_dir():
        raise HTTPException(status_code=400, detail=f"'cwd' is not a directory on the host: {cwd}")
    timeout = payload.get("timeout")
    # bool is an int in Python: without excluding it, `true` would pass as 1s.
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
    # limit=0 would return the whole audit (`lines[-0:]` is every line).
    if not 1 <= limit <= MAX_HISTORY:
        raise HTTPException(status_code=400, detail=f"'limit' must be from 1 to {MAX_HISTORY}")
    return JSONResponse({"entries": audit.read_recent(limit)})


def main() -> None:
    import uvicorn

    # 8766: next free port after the daemon (8765); the daemon passes its own.
    port = int(os.getenv("RINTHEL_HOSTEXECD_PORT", "8766"))
    print(f"[hostexecd] {time.strftime('%H:%M:%S')} starting on http://127.0.0.1:{port}")
    if auth.expected_token() is None:
        print("[hostexecd] WARNING: RINTHEL_HOSTEXECD_TOKEN is not set; every request will be a 401.")
    # One worker: there is no state to share, and one process per port.
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", workers=1)


if __name__ == "__main__":
    main()
