"""Los puertos de lifecycle: lo que una phase le pide al host donde corre la
Instance. El dominio los define; subprocess, socket, urllib, shutil y psutil
son adapters detrás (ADR 0004). El reloj es el ``Clock`` neutral de
``rinthel_tui/clock.py``."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from rinthel_tui.lifecycle.domain.types import ComposeService, Platform, ProcessHandle, RunResult


class Runner(Protocol):
    """Corre un comando hasta que termina. No levanta si el comando no existe
    o no arranca: devuelve rc 127 con el motivo en la salida. ``env`` es el
    delta sobre el entorno base, que el dominio nunca lee. Una cancelación
    detiene y recoge el grupo de procesos propio antes de propagarse."""

    async def run(
        self, cmd: Sequence[str], *, cwd: Path | None = None, env: Mapping[str, str] | None = None
    ) -> RunResult: ...


class Processes(Protocol):
    """Procesos de larga vida lanzados en segundo plano (llama-server,
    whisper, tts), cada uno en su propia sesión, con stdout y stderr
    anexados a ``log``. ``spawn`` devuelve el ``ProcessHandle`` y levanta ``SpawnFailed`` si no arranca.
    ``terminate`` pide parar (SIGTERM) y ``kill`` fuerza (SIGKILL) a todo el
    grupo del proceso; sobre uno que ya terminó no hacen nada. Parar no es
    inmediato: quien espera lo hace con ``Clock.sleep`` y ``is_alive``.
    ``stop_listeners`` pide parar (o, con ``force``, fuerza) a quien esté
    escuchando en ``port``, lo haya lanzado o no este proceso, y devuelve los
    pids a los que les llegó la señal (vacío si no hay nadie o no se lo pudo
    identificar). Nunca levanta."""

    async def spawn(
        self, argv: Sequence[str], *, log: Path, cwd: Path | None = None, env: Mapping[str, str] | None = None
    ) -> ProcessHandle: ...
    def is_alive(self, handle: ProcessHandle) -> bool: ...
    def terminate(self, handle: ProcessHandle) -> None: ...
    def kill(self, handle: ProcessHandle) -> None: ...
    async def stop_listeners(self, port: int, *, force: bool = False) -> list[int]: ...


class Probe(Protocol):
    """Pregunta si algo responde, sin levantar: ``port_open`` si hay alguien
    escuchando en ese puerto de la máquina; ``http_ok`` si la URL responde
    2xx dentro de ``timeout`` segundos. Todo lo demás (rechazo, 5xx, tiempo
    agotado) es ``False``."""

    async def port_open(self, port: int) -> bool: ...
    async def http_ok(self, url: str, timeout: float = 2.0) -> bool: ...


class HostInfo(Protocol):
    """Lo que la máquina dice de sí misma y las phases deciden con eso:
    ``which`` y ``find_nvcc`` devuelven la ruta o ``None`` si no está;
    ``cpu_count`` cuántos jobs paralelos aguanta un build (al menos 1);
    ``sha256`` el digest hex de un archivo ya bajado; ``platform`` la
    Platform del host; ``find_llama_server`` el ``llama-server`` que dejó un
    build en ``build_dir`` (o ``None`` si no hay): dónde lo deja el build
    depende de la Platform. ``which`` también conoce dónde instala cada
    Platform sus herramientas de build (CMake de Visual Studio en Windows).
    Nunca levantan salvo ``sha256`` sobre un archivo que no se puede leer
    (``OSError``)."""

    def platform(self) -> Platform: ...
    def which(self, name: str) -> str | None: ...
    def find_nvcc(self) -> str | None:
        """En el ``PATH`` primero; si no, el primer ``cuda*/bin/nvcc`` del toolkit instalado."""
        ...

    def cpu_count(self) -> int: ...
    def find_llama_server(self, build_dir: Path) -> Path | None: ...
    async def sha256(self, path: Path) -> str: ...


class PackageRegistry(Protocol):
    """La última versión publicada de un paquete, o ``None`` si no se pudo
    averiguar (sin red, registry caído, paquete desconocido). Nunca levanta."""

    async def latest(self, package: str, timeout: float = 5.0) -> str | None: ...


class Compose(Protocol):
    """Las intenciones sobre un servicio de un stack ``docker compose``; el
    argv de ``docker compose`` vive solo en el adapter. Cada operación
    devuelve el ``RunResult`` del comando (rc y salida) y no levanta por un rc
    distinto de cero: decidir qué hacer es de la phase.

    - ``up``: levanta el servicio (y baja los huérfanos del proyecto); con
      ``build`` reconstruye antes su imagen con esos ``--build-arg``; con
      ``wait`` espera a que quede sano.
    - ``recreate``: lo recrea sin tocar sus dependencias (toma un env nuevo).
    - ``down``: baja solo ese servicio, no el proyecto.
    - ``exec``: un comando dentro del contenedor que ya corre.
    - ``run``: un contenedor de un solo uso; ``env`` viaja por el entorno y
      no queda en el argv; ``build`` reconstruye la imagen antes.
    - ``logs``: las últimas ``tail`` líneas."""

    async def up(
        self, service: ComposeService, *, build: Mapping[str, str] | None = None, wait: bool = False
    ) -> RunResult: ...
    async def recreate(self, service: ComposeService) -> RunResult: ...
    async def down(self, service: ComposeService) -> RunResult: ...
    async def exec(self, service: ComposeService, cmd: Sequence[str]) -> RunResult: ...
    async def run(
        self, service: ComposeService, cmd: Sequence[str], *, env: Mapping[str, str] | None = None, build: bool = False
    ) -> RunResult: ...
    async def logs(self, service: ComposeService, *, tail: int) -> RunResult: ...


class DataDirs(Protocol):
    """Los directorios de datos que compose monta en contenedores que no
    corren como root. ``ensure`` crea ``path`` (con sus padres) si falta,
    para ``uid``:``gid``, y devuelve el dueño que ``path`` tiene al final: uno
    que ya existía conserva el suyo, y decidir si sirve es de la phase.
    Levanta ``DataDirError`` si no puede crearlo."""

    def ensure(self, path: Path, *, uid: int, gid: int) -> tuple[int, int]: ...
