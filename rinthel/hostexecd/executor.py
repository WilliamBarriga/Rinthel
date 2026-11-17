"""``subprocess.run`` with a timeout and no privilege escalation: a command runs
as the user that started ``hostexecd`` (the daemon's), without sudo. There is
no allowlist or blocklist of commands here or anywhere in this package:
anything that needs root fails on its own, at the operating system."""

from __future__ import annotations

import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

# For one-off checks and tweaks (GPU state, restarting a service, environment
# changes). Background process management is out of scope: a command that
# needs longer is not what ``/exec`` is for. A request may override it.
DEFAULT_TIMEOUT = 60
# Ceiling of the override: without it the model could ask for any timeout and
# keep this single-worker process busy.
MAX_TIMEOUT = 600
# Per stream (stdout and stderr apart): the output goes back whole into the
# model's context, and a ``cat`` of a large log would fill it. The head is kept
# and the total is said.
MAX_OUTPUT_BYTES = 50_000

HOME = str(Path.home())


@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    # Size of each stream before truncation: what the audit records.
    stdout_bytes: int
    stderr_bytes: int


def _read_capped(f) -> tuple[str, int]:
    """Up to ``MAX_OUTPUT_BYTES`` of ``f`` and its total size, with a notice
    at the end when it was cut."""
    total = f.seek(0, 2)
    f.seek(0)
    text = f.read(MAX_OUTPUT_BYTES).decode(errors="replace")
    if total > MAX_OUTPUT_BYTES:
        text += f"\n[hostexecd: output truncated to {MAX_OUTPUT_BYTES} of {total} bytes]\n"
    return text, total


def run_command(command: str, cwd: str | None, timeout: int | None) -> ExecResult:
    """Run ``command`` with ``shell=True`` in ``cwd`` (``$HOME`` by default).

    A timeout does not promise to kill the whole process tree: ``/bin/sh``
    sits in between, so a child that ignores SIGTERM can outlive it.

    Output is captured to temporary files, not pipes: a command that leaves
    something in the background (``app &``) hands it the shell's stdout and
    stderr, and with pipes the read would wait until that background process
    ends. With files, what was written is read as soon as the shell returns.
    """
    effective_timeout = timeout or DEFAULT_TIMEOUT
    start = time.monotonic()
    timed_out = False
    with (
        tempfile.TemporaryFile(mode="w+b") as stdout_f,
        tempfile.TemporaryFile(mode="w+b") as stderr_f,
    ):
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=cwd or HOME,
                timeout=effective_timeout,
                stdout=stdout_f,
                stderr=stderr_f,
            )
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = -1
        stdout, stdout_bytes = _read_capped(stdout_f)
        stderr, stderr_bytes = _read_capped(stderr_f)
    duration_ms = int((time.monotonic() - start) * 1000)
    return ExecResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        timed_out=timed_out,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
    )
