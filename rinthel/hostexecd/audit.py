"""Append-only audit of ``hostexecd``: every ``/exec`` is recorded here before
its answer goes back. One JSON object per line (JSONL), under the Instance's
data (``data/hostexecd/audit.jsonl``), never tracked: easy to ``tail -f`` by
hand and to read back for ``GET /history``. The process's own output goes to
``logs/hostexecd.log``, apart, so tracebacks never mix with the audit."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from rinthel_tui.instance import Instance


def log_path() -> Path:
    """The audit file of the Instance (``RINTHEL_INSTANCE_ROOT`` wins)."""
    return Instance.discover().data_dir / "hostexecd" / "audit.jsonl"


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
    """Append one entry. Best effort: the command already ran and its result is
    built, so a full disk or a permission error loses one audit line rather
    than turning the answer into a 500."""
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
    """The last ``limit`` entries, most recent first. The whole file is read:
    the audit of a single host grows too slowly to need an index."""
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
