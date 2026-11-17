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

from rinthel_tui.instance import Instance


def log_path() -> Path:
    """The audit log, under ``logs/`` at the Instance root (``RINTHEL_INSTANCE_ROOT`` wins)."""
    return Instance.discover().logs_dir / "hostexecd.log"


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
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_recent(limit: int = 20) -> list[dict[str, Any]]:
    """Últimas ``limit`` entradas, más reciente primero. Lee el archivo
    entero y se queda con la cola — el log de un daemon de un solo usuario
    no crece lo bastante rápido como para justificar un índice o un tail
    binario (comparar con ``tail`` en ``monitoring/adapters/log_file.py``, que
    sí lo necesita para el log de llama-server, mucho más verboso)."""
    path = log_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
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
