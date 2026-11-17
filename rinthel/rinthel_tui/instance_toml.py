"""``instance.toml`` as a raw file: the shared helper of the adapters that keep
their settings there, each one with its own keys. A writer re-reads the file
and changes only its part, so no owner overwrites another.

``tomllib`` (stdlib, read-only) parses; writing needs no new library: flat
keys and, at most, one-level tables. A small serializer covers that."""

from __future__ import annotations

import json
import os
import threading
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rinthel_tui.atomic_write import atomic_write

# One lock per file: each adapter is built with its own instance, so the
# exclusion cannot live in them. Reentrant so ``update`` can use ``read``.
_locks: dict[Path, threading.RLock] = {}
_locks_guard = threading.Lock()

Replace = Callable[[str, Path], None]


def _lock(path: Path) -> threading.RLock:
    key = path.resolve()
    with _locks_guard:
        return _locks.setdefault(key, threading.RLock())


def read(path: Path) -> dict[str, Any]:
    """The whole file, or ``{}`` if it does not exist. Lets ``OSError`` and
    ``tomllib.TOMLDecodeError`` through: each owner decides what they mean."""
    with _lock(path):
        if not path.exists():
            return {}
        with path.open("rb") as f:
            return tomllib.load(f)


def update(
    path: Path, change: Callable[[dict[str, Any]], dict[str, Any]], *, replace: Replace = os.replace
) -> dict[str, Any]:
    """Reads, applies ``change`` and writes the result, with no other thread of
    the process writing in between. Other processes only read it (covered by
    the atomic write). Returns what was written; if ``change`` raises,
    nothing is written."""
    with _lock(path):
        data = change(read(path))
        _write(path, data, replace)
        return data


def _write(path: Path, data: dict[str, Any], replace: Replace) -> None:
    flat = [f"{key} = {_value(v)}" for key, v in data.items() if v is not None and not isinstance(v, dict)]
    tables = [
        f"\n[{name}]\n" + "".join(f"{key} = {_value(v)}\n" for key, v in table.items() if v is not None)
        for name, table in data.items()
        if isinstance(table, dict)
    ]
    atomic_write(path, "".join(line + "\n" for line in flat) + "".join(tables), replace=replace)


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        # A JSON string is a valid TOML basic string: it escapes quotes,
        # backslashes and newlines.
        return json.dumps(value, ensure_ascii=False)
    raise TypeError(f"tipo no soportado en instance.toml: {type(value)!r}")
