"""Log de auditoría append-only para hostexecd — cada ejecución de /exec se
apenda acá antes de devolver la respuesta. Nunca a Understory (ver
plans/rinthel-host-exec.md, decisión de diseño 7: Understory es una base de
conocimiento curada — conceptos markdown tipo OKF —, no un sumidero de
telemetría transaccional; y además hay una regla ya existente de nunca usar
las tools de escritura de Understory, ni con autorización).

Formato: una línea JSON por entrada (JSONL) en logs/hostexecd.log — fácil
de ``tail -f`` a mano y de parsear para ``GET /history``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

# hostexecd/audit.py -> repo root (mismo criterio que rinthel_tui/daemon.py
# usa para ubicar su propio .env desde la raíz del repo).
_REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = _REPO_ROOT / "logs" / "hostexecd.log"


def record(
    *,
    command: str,
    cwd: str | None,
    exit_code: int,
    duration_ms: int,
    stdout_len: int,
    stderr_len: int,
    timed_out: bool,
) -> None:
    """Apenda una entrada. Best-effort: si escribir el log falla (disco
    lleno, permisos), no debe tirar abajo la respuesta de ``/exec`` — el
    comando ya corrió y su resultado real ya está armado; perder una línea
    de auditoría no es motivo para devolver un 500 sobre eso."""
    entry = {
        "ts": time.time(),
        "command": command,
        "cwd": cwd,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "stdout_len": stdout_len,
        "stderr_len": stderr_len,
        "timed_out": timed_out,
    }
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_recent(limit: int = 20) -> list[dict[str, Any]]:
    """Últimas ``limit`` entradas, más reciente primero. Lee el archivo
    entero y se queda con la cola — el log de un daemon de un solo usuario
    no crece lo bastante rápido como para justificar un índice o un tail
    binario (comparar con ``_tail_lines`` en ``rinthel_tui/daemon.py``, que
    sí lo necesita para el log de llama-server, mucho más verboso)."""
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    out.reverse()
    return out
