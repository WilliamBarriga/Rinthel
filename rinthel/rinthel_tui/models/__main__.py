"""The offline Local model commands: ``python -m rinthel_tui.models list``,
``python -m rinthel_tui.models use <id>`` and
``python -m rinthel_tui.models off stt|tts``. An offline composition root: it
builds the real adapters from the Instance, like ``create_app`` does for the
daemon.

``use`` and ``off`` only write ``instance.toml``: the next boot starts (or
leaves out) the service. With the Capability's managed service still
listening they refuse (stop the services first, or switch from the daemon,
which restarts it). Voice (``stt``/``tts``) is Linux only."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from rinthel_tui.config import RinthelConfig, default_config
from rinthel_tui.instance import Instance
from rinthel_tui.lifecycle.composition import real_host_info
from rinthel_tui.lifecycle.adapters.socket_probe import SocketProbe
from rinthel_tui.lifecycle.domain.ports import Probe
from rinthel_tui.lifecycle.domain.types import Platform
from rinthel_tui.lifecycle.services import MODEL_SERVICES
from rinthel_tui.models.adapters.json_catalog import JsonCatalog
from rinthel_tui.models.adapters.toml_active import TomlActiveModels
from rinthel_tui.models.domain.errors import CatalogUnavailable, NotActivable, UnknownModel
from rinthel_tui.models.domain.models import activable
from rinthel_tui.models.domain.types import VOICE, Capability


def main(argv: list[str] | None = None, *, probe: Probe | None = None, platform: Platform | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m rinthel_tui.models")
    parser.add_argument("--root", type=Path, help="raíz explícita (default: Instance.discover())")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("use").add_argument("id")
    sub.add_parser("off").add_argument("capability", choices=VOICE)
    args = parser.parse_args(argv)

    instance = Instance(args.root) if args.root else Instance.discover()
    catalog = JsonCatalog(instance.models_catalog_path)
    active = TomlActiveModels(instance.instance_toml_path)
    try:
        if args.command == "list":
            return _list(catalog, active)
        cfg = default_config(instance, platform=platform or real_host_info().platform())
        if args.command == "off":
            return _off(cfg, active, args.capability, probe or SocketProbe())
        return _use(cfg, catalog, active, args.id, probe or SocketProbe())
    except CatalogUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _list(catalog: JsonCatalog, active: TomlActiveModels) -> int:
    for entry in catalog.entries():
        model = entry.model
        mark = "*" if model is not None and active.get(model.capability) == entry.id else " "
        what = f"{model.name} [{model.capability}]" if model is not None else ""
        problem = f"  — no activable: {entry.problem}" if entry.problem else ""
        print(f"{mark} {entry.id}  {what}{problem}")
    return 0


def _use(cfg: RinthelConfig, catalog: JsonCatalog, active: TomlActiveModels, model_id: str, probe: Probe) -> int:
    try:
        model = activable(catalog, model_id)
    except UnknownModel:
        print(f"error: Local model desconocido: {model_id}", file=sys.stderr)
        return 2
    except NotActivable as exc:
        print(f"error: {model_id} no es activable: {exc}", file=sys.stderr)
        return 2
    if _refused(cfg, model.capability, probe):
        return 2
    active.set(model.capability, model.id)
    print(f"Local model activo de {model.capability}: {model.id} — arranca en el próximo boot", file=sys.stderr)
    return 0


def _off(cfg: RinthelConfig, active: TomlActiveModels, capability: Capability, probe: Probe) -> int:
    if _refused(cfg, capability, probe):
        return 2
    active.clear(capability)
    print(f"{capability} apagado — su servicio no arranca en el próximo boot", file=sys.stderr)
    return 0


def _refused(cfg: RinthelConfig, capability: Capability, probe: Probe) -> bool:
    """Voice off Linux, or the Capability's service still listening."""
    if capability in VOICE and cfg.platform != "linux":
        print("error: la voz es solo de Linux", file=sys.stderr)
        return True
    service = MODEL_SERVICES[capability]
    port = service.port_of(cfg) if service.port_of is not None else None
    if port is not None and asyncio.run(probe.port_open(port)):
        print(
            f"error: {service.display_name} está corriendo en :{port} — pará los servicios (TERMINATE) "
            "o cambiá el modelo desde el daemon",
            file=sys.stderr,
        )
        return True
    return False


if __name__ == "__main__":
    sys.exit(main())
