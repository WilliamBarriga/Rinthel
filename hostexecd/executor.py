"""subprocess.run con timeout, sin elevar privilegios — hereda el usuario
del proceso del daemon (tarkark, uid 1000, sin sudo). Ver
plans/rinthel-host-exec.md, decisión de diseño 2: cualquier comando que
necesite root falla solo, a nivel de sistema operativo — no hay allowlist
ni blocklist de comandos acá, ni en ningún otro módulo de este paquete."""

from __future__ import annotations

import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

# Default razonable para comandos interactivos/chequeos puntuales (el caso
# de uso real: reiniciar el daemon/stack de Rinthel, chequeos de GPU/estado,
# tweaks de entorno). Este daemon no administra procesos de fondo (ver
# "Fuera de alcance" del plan) — un comando que necesita correr más que
# esto no es lo que /exec está pensado para cubrir. Overrideable por
# request (campo "timeout" del body).
DEFAULT_TIMEOUT = 60

HOME = str(Path.home())


@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool


def run_command(command: str, cwd: str | None, timeout: int | None) -> ExecResult:
    """Corre ``command`` con ``shell=True``, ``cwd=cwd or HOME``, capturando
    stdout/stderr como texto. Nunca eleva privilegios: mismo usuario que
    corre el daemon, sin ``sudo``/``su`` en ningún punto.

    Un timeout no garantiza matar toda la jerarquía de procesos —
    ``shell=True`` interpone ``/bin/sh``, así que un hijo que ignora
    SIGTERM (o sus propios hijos) puede sobrevivir al timeout del padre.
    Límite ya documentado de ``subprocess.run(shell=True, timeout=...)``,
    no algo que este módulo intente resolver (este daemon es de alcance
    bloqueante-sin-gestión-de-procesos-de-fondo por diseño, ver el plan).

    stdout/stderr se capturan a archivos temporales, NO con
    ``capture_output=True`` (pipes). Un comando que backgroundea algo
    (``spotify &``, con o sin redirección propia — ``shell=True`` usa
    ``/bin/sh``, no bash, así que `&>` de la LLM no siempre hace lo que
    parece) deja a ese proceso de fondo con los mismos file descriptors de
    stdout/stderr que el shell padre. Con pipes, ``communicate()`` no
    vuelve hasta que TODO lo que heredó el pipe cierre su extremo de
    escritura — es decir, hasta que el proceso de fondo termine, no cuando
    el shell que lo lanzó ya volvió. Con archivos, no hay ese problema: se
    lee lo que se haya escrito hasta que el shell (el único proceso que
    ``Popen``/``wait()`` realmente espera) termina.
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
        stdout_f.seek(0)
        stderr_f.seek(0)
        stdout = stdout_f.read().decode(errors="replace")
        stderr = stderr_f.read().decode(errors="replace")
    duration_ms = int((time.monotonic() - start) * 1000)
    return ExecResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        timed_out=timed_out,
    )
