"""Los dobles de los puertos de lifecycle (ADR 0005). Cada uno inyecta fallos
con ``fail_next(op, exc)``, donde ``op`` es el nombre del método del puerto, y
todos pueden compartir un ``log`` de eventos para afirmar el orden."""

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rinthel_tui.clock import Clock, ManualClock
from rinthel_tui.faults import FailureQueue
from rinthel_tui.lifecycle.domain.errors import SpawnFailed
from rinthel_tui.lifecycle.domain.host import Host
from rinthel_tui.lifecycle.domain.types import ComposeService, Platform, ProcessHandle, RunResult


class _Double(FailureQueue):
    def __init__(self, log: list[tuple] | None = None) -> None:
        self.log: list[tuple] = log if log is not None else []

    def _enter(self, op: str, *event: object) -> None:  # type: ignore[override]
        self.log.append((op, *event))
        super()._enter(op)


@dataclass(frozen=True)
class RunCall:
    cmd: tuple[str, ...]
    cwd: Path | None
    env: Mapping[str, str] | None


class FakeRunner(_Double):
    """Guion por comando: lo no escrito es un comando que no existe (rc 127),
    salvo tras ``succeed_by_default``. ``script_rcs`` escribe una tanda de
    respuestas: contesta así las primeras veces y repite la última.

    ``script_program`` fija el rc de todo comando de un programa (``git``,
    ``cmake``) sin repetir su argv, y ``on_success`` es lo que ese programa deja
    en el disco al terminar con rc 0 (un ``curl`` que escribe el archivo): se
    llama con el ``RunCall``. ``on_failure`` hace lo mismo con rc no cero,
    para los archivos parciales que deja un comando interrumpido."""

    def __init__(self, log: list[tuple] | None = None) -> None:
        super().__init__(log)
        self._script: dict[tuple[str, ...], list[RunResult]] = {}
        self._programs: dict[str, RunResult] = {}
        self._effects: dict[str, Callable[[RunCall], None]] = {}
        self._failure_effects: dict[str, Callable[[RunCall], None]] = {}
        self._default: RunResult | None = None
        self.calls: list[RunCall] = []

    def script(self, cmd: Sequence[str], *, rc: int = 0, output: str = "") -> None:
        self._script[tuple(cmd)] = [RunResult(rc, output)]

    def script_rcs(self, cmd: Sequence[str], rcs: Sequence[int]) -> None:
        self._script[tuple(cmd)] = [RunResult(rc, "") for rc in rcs]

    def script_program(self, program: str, *, rc: int, output: str = "") -> None:
        self._programs[program] = RunResult(rc, output)

    def succeed_by_default(self) -> None:
        self._default = RunResult(0, "")

    def on_success(self, program: str, effect: Callable[["RunCall"], None]) -> None:
        self._effects[program] = effect

    def on_failure(self, program: str, effect: Callable[["RunCall"], None]) -> None:
        """Efecto de un comando fallido, como los bytes de una descarga cortada."""
        self._failure_effects[program] = effect

    def ran(self, program: str) -> list["RunCall"]:
        return [call for call in self.calls if call.cmd[0] == program]

    async def run(
        self, cmd: Sequence[str], *, cwd: Path | None = None, env: Mapping[str, str] | None = None
    ) -> RunResult:
        self._enter("run", tuple(cmd))
        call = RunCall(tuple(cmd), cwd, env)
        self.calls.append(call)
        queue = self._script.get(tuple(cmd))
        if queue:
            result = queue.pop(0) if len(queue) > 1 else queue[0]
        elif cmd[0] in self._programs:
            result = self._programs[cmd[0]]
        elif self._default is not None:
            result = self._default
        else:
            return RunResult(127, f"{cmd[0]}: not found")
        if result.rc == 0 and (effect := self._effects.get(cmd[0])) is not None:
            effect(call)
        if result.rc != 0 and (effect := self._failure_effects.get(cmd[0])) is not None:
            effect(call)
        return result


@dataclass(frozen=True)
class Spawn:
    argv: tuple[str, ...]
    log: Path
    cwd: Path | None
    env: Mapping[str, str] | None
    handle: ProcessHandle


class FakeProcesses(_Double):
    """Procesos de mentira: por defecto viven hasta que se les pide parar.
    ``script`` fija el comportamiento de un argv: ``ignore_term`` (solo muere
    con ``kill``), ``exits`` (muere solo apenas arranca), ``missing`` (no arranca).
    ``listen(port, handle)`` deja un proceso escuchando en un puerto: ``stop_listeners``
    lo para como lo pararía una señal (``ignore_term`` solo cae con ``force``)."""

    def __init__(self, log: list[tuple] | None = None) -> None:
        super().__init__(log)
        self._behaviour: dict[tuple[str, ...], dict[str, bool]] = {}
        self._alive: set[ProcessHandle] = set()
        self._stubborn: set[ProcessHandle] = set()
        self._next_pid = 1000
        self._listeners: dict[int, list[ProcessHandle]] = {}
        self.spawns: list[Spawn] = []

    def listen(self, port: int, handle: ProcessHandle) -> None:
        self._alive.add(handle)
        self._listeners.setdefault(port, []).append(handle)

    def script(self, argv: Sequence[str], *, ignore_term: bool = False, exits: bool = False, missing: bool = False) -> None:
        self._behaviour[tuple(argv)] = {"ignore_term": ignore_term, "exits": exits, "missing": missing}

    async def spawn(
        self, argv: Sequence[str], *, log: Path, cwd: Path | None = None, env: Mapping[str, str] | None = None
    ) -> ProcessHandle:
        self._enter("spawn", tuple(argv))
        behaviour = self._behaviour.get(tuple(argv), {})
        if behaviour.get("missing"):
            raise SpawnFailed(f"{argv[0]}: not found")
        self._next_pid += 1
        handle = ProcessHandle(self._next_pid)
        self.spawns.append(Spawn(tuple(argv), log, cwd, env, handle))
        if not behaviour.get("exits"):
            self._alive.add(handle)
        if behaviour.get("ignore_term"):
            self._stubborn.add(handle)
        return handle

    def is_alive(self, handle: ProcessHandle) -> bool:
        return handle in self._alive

    def terminate(self, handle: ProcessHandle) -> None:
        self._enter("terminate", handle)
        if handle not in self._stubborn:
            self._alive.discard(handle)

    def kill(self, handle: ProcessHandle) -> None:
        self._enter("kill", handle)
        self._alive.discard(handle)

    async def stop_listeners(self, port: int, *, force: bool = False) -> list[int]:
        self._enter("stop_listeners", port, force)
        listening = [h for h in self._listeners.get(port, []) if h in self._alive]
        for handle in listening:
            if force or handle not in self._stubborn:
                self._alive.discard(handle)
        return [h.pid for h in listening]


class FakeProbe(_Double):
    """Respuestas por tanda: ``script_port(8080, [True, True, False])`` contesta
    así las tres primeras veces y repite la última. Lo no escrito es ``False``."""

    def __init__(self, log: list[tuple] | None = None, *, clock: Clock | None = None) -> None:
        super().__init__(log)
        self._answers: dict[tuple[str, object], list[bool]] = {}
        self._clock = clock
        self.http_asked_at: list[datetime] = []
        """Cuándo se preguntó cada ``http_ok``, si el doble tiene reloj."""

    def script_port(self, port: int, answers: bool | Sequence[bool]) -> None:
        self._answers[("port", port)] = [answers] if isinstance(answers, bool) else list(answers)

    def script_http(self, url: str, answers: bool | Sequence[bool]) -> None:
        self._answers[("http", url)] = [answers] if isinstance(answers, bool) else list(answers)

    def _answer(self, key: tuple[str, object]) -> bool:
        queue = self._answers.get(key)
        if not queue:
            return False
        return queue.pop(0) if len(queue) > 1 else queue[0]

    async def port_open(self, port: int) -> bool:
        self._enter("port_open", port)
        return self._answer(("port", port))

    async def http_ok(self, url: str, timeout: float = 2.0) -> bool:
        self._enter("http_ok", url)
        if self._clock is not None:
            self.http_asked_at.append(self._clock.now())
        return self._answer(("http", url))


class FakeHostInfo(_Double):
    """El host que le toca al test: herramientas instaladas (``install``), un
    toolkit de CUDA (``install_cuda``), cuántas CPU tiene (``cpus``) y su
    Platform (``os``), que el test cambia."""

    def __init__(self, *, cpus: int = 4, os: Platform = "linux", log: list[tuple] | None = None) -> None:
        super().__init__(log)
        self.os: Platform = os
        self._tools: dict[str, str] = {}
        self._cuda: str | None = None
        self.cpus = cpus

    def install(self, name: str, path: str) -> None:
        self._tools[name] = path

    def install_cuda(self, nvcc_path: str) -> None:
        self._cuda = nvcc_path

    def platform(self) -> Platform:
        self._enter("platform")
        return self.os

    def which(self, name: str) -> str | None:
        self._enter("which", name)
        return self._tools.get(name)

    def find_nvcc(self) -> str | None:
        self._enter("find_nvcc")
        return self._tools.get("nvcc") or self._cuda

    def cpu_count(self) -> int:
        self._enter("cpu_count")
        return self.cpus

    async def sha256(self, path: Path) -> str:
        self._enter("sha256", path)
        return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeRegistry(_Double):
    """Las versiones publicadas de cada paquete (``published``)."""

    def __init__(self, published: Mapping[str, str] | None = None, *, log: list[tuple] | None = None) -> None:
        super().__init__(log)
        self._published = dict(published or {})

    async def latest(self, package: str, timeout: float = 5.0) -> str | None:
        self._enter("latest", package)
        return self._published.get(package)


class FakeCompose(_Double):
    """Graba intenciones (``up``, ``down``...) en ``calls`` y lleva qué
    servicios corren. Un servicio fuera de ``known`` no existe en el compose
    file (rc 1). ``fail_rc(op, rc)`` hace que la próxima ``op`` termine con ese
    rc, como un ``docker compose`` que falla; ``fail_next`` levanta."""

    def __init__(self, *, known: Sequence[str] | None = None, log: list[tuple] | None = None) -> None:
        super().__init__(log)
        self._known = set(known) if known is not None else None
        self.running: set[str] = set()
        self.calls: list[tuple] = []
        self.requests: list[tuple[str, ComposeService]] = []
        """Cada operación con el ``ComposeService`` completo (perfil y entorno incluidos)."""
        self._rcs: dict[str, list[RunResult]] = {}

    def fail_rc(self, op: str, rc: int, output: str = "") -> None:
        self._rcs.setdefault(op, []).append(RunResult(rc, output))

    def _do(self, op: str, service: ComposeService, *detail: object) -> RunResult | None:
        self._enter(op, service.name, *detail)
        self.calls.append((op, service.name, *detail))
        self.requests.append((op, service))
        if self._rcs.get(op):
            return self._rcs[op].pop(0)
        if self._known is not None and service.name not in self._known:
            return RunResult(1, f"no such service: {service.name}")
        return None

    async def up(
        self, service: ComposeService, *, build: Mapping[str, str] | None = None, wait: bool = False
    ) -> RunResult:
        failed = self._do("up", service, dict(build) if build is not None else None, wait)
        if failed is None:
            self.running.add(service.name)
        return failed or RunResult(0, "")

    async def recreate(self, service: ComposeService) -> RunResult:
        failed = self._do("recreate", service)
        if failed is None:
            self.running.add(service.name)
        return failed or RunResult(0, "")

    async def down(self, service: ComposeService) -> RunResult:
        failed = self._do("down", service)
        if failed is None:
            self.running.discard(service.name)
        return failed or RunResult(0, "")

    async def exec(self, service: ComposeService, cmd: Sequence[str]) -> RunResult:
        failed = self._do("exec", service, tuple(cmd))
        if failed is not None:
            return failed
        return RunResult(0, "") if service.name in self.running else RunResult(1, "service is not running")

    async def run(
        self, service: ComposeService, cmd: Sequence[str], *, env: Mapping[str, str] | None = None, build: bool = False
    ) -> RunResult:
        return self._do("run", service, tuple(cmd), dict(env or {}), build) or RunResult(0, "")

    async def logs(self, service: ComposeService, *, tail: int) -> RunResult:
        return self._do("logs", service, tail) or RunResult(0, "")


class FakeDataDirs(_Double):
    """Los directorios del host con su dueño: ``create`` siembra uno que ya
    existía (``owner_of`` lo lee de vuelta)."""

    def __init__(self, *, log: list[tuple] | None = None) -> None:
        super().__init__(log)
        self._owners: dict[Path, tuple[int, int]] = {}

    def create(self, path: Path, *, uid: int, gid: int) -> None:
        self._owners[path] = (uid, gid)

    def owner_of(self, path: Path) -> tuple[int, int] | None:
        return self._owners.get(path)

    def ensure(self, path: Path, *, uid: int, gid: int) -> tuple[int, int]:
        self._enter("ensure", path)
        return self._owners.setdefault(path, (uid, gid))


class FakeReport:
    """``PhaseReport`` que graba ``(kind, mensaje)`` en orden. El texto no es
    contrato (ADR 0005, regla 4): se afirma sobre cuántos hay de cada clase."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def _of(self, kind: str) -> list[str]:
        return [msg for k, msg in self.events if k == kind]

    infos = property(lambda self: self._of("info"))
    successes = property(lambda self: self._of("success"))
    warnings = property(lambda self: self._of("warn"))
    errors = property(lambda self: self._of("error"))

    def info(self, msg: str) -> None:
        self.events.append(("info", msg))

    def success(self, msg: str) -> None:
        self.events.append(("success", msg))

    def warn(self, msg: str) -> None:
        self.events.append(("warn", msg))

    def error(self, msg: str) -> None:
        self.events.append(("error", msg))


class FakeHost(Host):
    """Un ``Host`` de dobles; ``log`` es el que comparten todos."""


def fake_host(**overrides) -> tuple[FakeHost, list[tuple]]:
    """Un ``Host`` con un doble por puerto, todos con el mismo ``log``. Se
    reemplaza uno con ``overrides`` (``fake_host(clock=ManualClock(...))``)."""
    log: list[tuple] = []
    clock = overrides.get("clock", ManualClock())
    ports = {
        "runner": FakeRunner(log),
        "processes": FakeProcesses(log),
        "compose": FakeCompose(log=log),
        "probe": FakeProbe(log, clock=clock),
        "clock": clock,
        "host_info": FakeHostInfo(log=log),
        "registry": FakeRegistry(log=log),
        "data_dirs": FakeDataDirs(log=log),
        **overrides,
    }
    return FakeHost(**ports), log
