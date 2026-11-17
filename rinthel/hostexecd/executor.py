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
# Techo del override por request: sin él, la LLM podía pedir un timeout
# arbitrario y dejar /exec colgado — este daemon es de un solo worker.
MAX_TIMEOUT = 600
# Tope por stream (stdout y stderr por separado): la salida vuelve entera al
# contexto del modelo, y un `cat` de un log grande se lo comería. Se queda
# con el principio y avisa cuánto había en total.
MAX_OUTPUT_BYTES = 50_000

HOME = str(Path.home())


@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    # Tamaño real de cada stream antes de truncar — lo que va al audit log.
    stdout_bytes: int
    stderr_bytes: int


def _read_capped(f) -> tuple[str, int]:
    """Lee hasta MAX_OUTPUT_BYTES de ``f`` (ya escrito, en cualquier
    posición) y devuelve ``(texto, bytes_totales)``, con un aviso al final
    si hubo que cortar."""
    total = f.seek(0, 2)
    f.seek(0)
    text = f.read(MAX_OUTPUT_BYTES).decode(errors="replace")
    if total > MAX_OUTPUT_BYTES:
        text += f"\n[hostexecd: salida truncada a {MAX_OUTPUT_BYTES} de {total} bytes]\n"
    return text, total


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
