"""Estado de contenedores Docker para MonitorScreen.

El estado ONLINE/OFFLINE de Understory/Pithagoras/llama-server ya lo cubre
``tui.widgets.service_badge.ServiceBadge`` (Fase 3) polleando su propia URL
— esto se limita a lo que ese widget no ve: qué contenedores hay realmente
arriba en cada proyecto (nombre/estado/puertos/uptime), vía
``docker compose ps``. Nunca levanta excepción: un proyecto caído, sin
clonar, o sin Docker disponible simplemente devuelve una lista vacía.
"""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DockerContainer:
    name: str
    state: str
    ports: str
    status: str


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


async def docker_compose_ps(directory: Path) -> list[DockerContainer]:
    directory = Path(directory)
    if not directory.is_dir():
        return []
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "ps", "--format", "json",
            cwd=str(directory),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
    except OSError:
        return []
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
