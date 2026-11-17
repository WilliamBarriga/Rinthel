"""Los tipos del dominio de lifecycle: lo que cruzan los puertos y lo que
devuelven las phases. Sin ``RinthelConfig`` ni DTOs (ADR 0004)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# El sistema anfitrión de la Instance (ver **Platform** en GLOSSARY.md).
Platform = Literal["linux", "windows"]


@dataclass(frozen=True)
class RunResult:
    """Lo que devuelve un comando: código de salida y salida combinada
    (stdout + stderr). ``rc`` 127 es un comando que no pudo arrancar."""

    rc: int
    output: str


@dataclass(frozen=True)
class ProcessHandle:
    """Un proceso que lanzó ``Processes.spawn``. Para las phases es opaco: lo
    único que hacen es devolvérselo al puerto; ``pid`` es para mostrárselo al
    admin."""

    pid: int


@dataclass(frozen=True)
class ComposeService:
    """Un servicio de un stack ``docker compose``: la carpeta del compose
    file, su nombre, el profile que lo activa (si tiene) y el entorno que
    necesita para interpolar su compose file (delta sobre el del host)."""

    directory: Path
    name: str
    profile: str | None = None
    env: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class ServiceSpec:
    """Lo que las phases saben de un servicio gestionado, ya armado a partir de
    la config: nombre, puerto (``None`` en uno sin puerto propio), si está habilitado y cómo se espera a que responda
    (``ready_url``, ``None`` si no expone healthcheck HTTP). El polling arranca
    en ``ready_poll_interval``, se multiplica por ``ready_poll_backoff`` en cada
    vuelta sin respuesta y se capea en ``ready_poll_max_interval``."""

    display_name: str
    port: int | None = None
    enabled: bool = True
    ready_url: str | None = None
    ready_timeout: int = 90
    ready_poll_interval: float = 2.0
    ready_poll_backoff: float = 1.5
    ready_poll_max_interval: float = 10.0
    on_timeout_hint: str | None = None


@dataclass(frozen=True, kw_only=True)
class LocalProcessSpec(ServiceSpec):
    """Un binario local: su ``argv`` y ``env`` (delta sobre el del host), el
    ``log`` donde anexa su salida, los ``files`` que lee al arrancar (se
    reescriben en cada spawn) y los ``dirs`` que necesita existentes."""

    argv: tuple[str, ...]
    log: Path
    env: Mapping[str, str] = field(default_factory=dict)
    files: Mapping[Path, str] = field(default_factory=dict)
    dirs: tuple[Path, ...] = ()


@dataclass(frozen=True, kw_only=True)
class DockerComposeSpec(ServiceSpec):
    """Un servicio de un stack ``docker compose``. ``build_args`` (solo el
    portal) es lo que reconstruye su imagen antes de
    levantar; ``npm_build_args`` son pares (build arg, paquete npm): el build
    recibe la última versión publicada del paquete."""

    stack: ComposeService
    build_args: tuple[str, ...] | None = None
    npm_build_args: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class UnitOutcome:
    """El resultado de una unidad de un plan (un servicio que se aplicó o
    se paró). ``api/lifecycle/routes.py`` lo traduce a ``ServiceOutcome``."""

    service: str
    ok: bool
    message: str
