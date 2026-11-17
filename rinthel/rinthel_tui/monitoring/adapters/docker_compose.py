"""``ContainerStatus`` sobre ``docker compose ps``: qué contenedores hay en
cada proyecto compose de la Instance (nombre, estado, puertos, uptime). Nunca
levanta: un proyecto caído, sin clonar, o sin Docker disponible devuelve una
lista vacía."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.services import DOCKER_SERVICES
from rinthel_tui.monitoring.domain.types import DockerContainer


def _parse_compose_ps(raw: str) -> list[dict]:
    """`docker compose ps --format json` no es estable entre versiones:
    unas emiten un array JSON, otras JSON-lines (un objeto por línea)."""
    raw = raw.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        pass
    rows = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _ports_of(row: dict) -> str:
    publishers = row.get("Publishers")
    if publishers:
        return ",".join(
            f"{p.get('PublishedPort', '')}->{p.get('TargetPort', '')}" for p in publishers if p.get("PublishedPort")
        ) or "-"
    return row.get("Ports", "") or "-"


class DockerComposeContainers:
    """``cfg_of`` es el ``cfg`` vivo: cada lectura ve el de ese momento (un
    ``POST /config`` lo reemplaza). ``docker`` es el ejecutable a correr (el
    del PATH por defecto); los tests pasan uno falso. ``spawn`` lanza el
    subproceso: un test lo cambia para forzar la carrera entre cancelar y que
    el ``ps`` salga solo."""

    def __init__(
        self,
        cfg_of: Callable[[], RinthelConfig],
        *,
        docker: str = "docker",
        spawn: Callable[..., Awaitable[Any]] = asyncio.create_subprocess_exec,
    ) -> None:
        self._cfg_of = cfg_of
        self._docker = docker
        self._spawn = spawn

    async def containers(self) -> list[DockerContainer]:
        # Un ``ps`` por dir distinto: los servicios que comparten proyecto
        # compose (hoy todos, en la raíz de la Instance) comparten
        # también su lista de contenedores.
        cfg = self._cfg_of()
        containers: list[DockerContainer] = []
        for directory in dict.fromkeys(svc.dir_of(cfg) for svc in DOCKER_SERVICES):
            containers += await self._ps(Path(directory))
        return containers

    async def _ps(self, directory: Path) -> list[DockerContainer]:
        if not directory.is_dir():
            return []
        try:
            proc = await self._spawn(
                self._docker, "compose", "ps", "--format", "json",
                cwd=str(directory),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError:
            return []
        try:
            out, _ = await proc.communicate()
        except BaseException:
            # Cancelada (el cliente del monitor se fue): no dejar el ps vivo.
            with contextlib.suppress(ProcessLookupError):  # ya había salido
                proc.kill()
            await proc.wait()
            raise
        if proc.returncode != 0:
            return []
        return [
            DockerContainer(
                name=row.get("Name", "?"),
                state=row.get("State", "?"),
                ports=_ports_of(row),
                status=row.get("Status", "?"),
            )
            for row in _parse_compose_ps(out.decode(errors="replace"))
        ]
