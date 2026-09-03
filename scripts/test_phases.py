#!/usr/bin/env python3
"""Script de prueba manual para rinthel_tui.lifecycle — no es parte del
paquete instalado, se corre suelto contra la infra real antes de conectar
las fases a una Screen de Textual (Fase 3 del plan de migración).

Uso:
  .venv/bin/python scripts/test_phases.py list
  .venv/bin/python scripts/test_phases.py <fase-o-lista> [--port N] [--timeout N] [--no-cache]

Fases individuales: check_docker, spawn_llama, wait_llama, kill_llama,
  stop_understory, stop_pithagoras, wait_port_free, up_understory,
  build_up_pithagoras, capture_profile, install_preflight,
  install_clone_llamacpp, install_build_llamacpp, install_download_model,
  install_setup_pithagoras, install_setup_understory
Listas declarativas (mismo orden que rinthel-up/down/reload.sh):
  boot, down, reload_shutdown, reload_boot, reload_rebuild, install
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rinthel_tui.config import CONFIG
from rinthel_tui.lifecycle import install, phases, specs
from rinthel_tui.lifecycle.capture_profile import capture_profile as _capture_profile
from rinthel_tui.lifecycle.runner import PhaseFailed, run_phase_list


class PrintReport:
    def info(self, msg: str) -> None:
        print(f"  · {msg}")

    def success(self, msg: str) -> None:
        print(f"  ● {msg}")

    def warn(self, msg: str) -> None:
        print(f"  ▲ {msg}")

    def error(self, msg: str) -> None:
        print(f"  ✖ {msg}")


PHASE_FNS = {
    "check_docker": lambda cfg, report, args: phases.phase_check_docker(cfg, report),
    "spawn_llama": lambda cfg, report, args: phases.phase_spawn_llama_server(cfg, report),
    "wait_llama": lambda cfg, report, args: phases.phase_wait_llama_ready(cfg, report, timeout=args.timeout),
    "kill_llama": lambda cfg, report, args: phases.phase_kill_llama_server(cfg, report),
    "stop_understory": lambda cfg, report, args: phases.phase_stop_understory(cfg, report),
    "stop_pithagoras": lambda cfg, report, args: phases.phase_stop_pithagoras(cfg, report),
    "wait_port_free": lambda cfg, report, args: phases.phase_wait_port_free(cfg, report, port=args.port),
    "up_understory": lambda cfg, report, args: phases.phase_up_understory(cfg, report),
    "build_up_pithagoras": lambda cfg, report, args: phases.phase_build_up_pithagoras(
        cfg, report, no_cache=args.no_cache
    ),
    "capture_profile": lambda cfg, report, args: _capture_profile(cfg, report),
    "install_preflight": lambda cfg, report, args: install.phase_install_preflight(cfg, report),
    "install_clone_llamacpp": lambda cfg, report, args: install.phase_install_clone_llamacpp(cfg, report),
    "install_build_llamacpp": lambda cfg, report, args: install.phase_install_build_llamacpp(cfg, report),
    "install_download_model": lambda cfg, report, args: install.phase_install_download_model(cfg, report),
    "install_setup_pithagoras": lambda cfg, report, args: install.phase_install_setup_pithagoras(cfg, report),
    "install_setup_understory": lambda cfg, report, args: install.phase_install_setup_understory(cfg, report),
}

SPEC_LISTS = {
    "boot": specs.BOOT_PHASES,
    "down": specs.DOWN_PHASES,
    "reload_shutdown": specs.RELOAD_SHUTDOWN_PHASES,
    "reload_boot": specs.RELOAD_BOOT_PHASES,
    "reload_rebuild": specs.RELOAD_REBUILD_PHASES,
    "install": specs.INSTALL_PHASES,
}


async def _main(args: argparse.Namespace) -> int:
    cfg = CONFIG
    cfg.apply_env()
    report = PrintReport()

    if args.target in PHASE_FNS:
        try:
            await PHASE_FNS[args.target](cfg, report, args)
        except phases.PhaseError as exc:
            report.error(f"fase falló: {exc}")
            return 1
    elif args.target in SPEC_LISTS:
        try:
            await run_phase_list(cfg, SPEC_LISTS[args.target], report)
        except PhaseFailed as exc:
            report.error(f"secuencia cortada en '{exc.label}': {exc.cause}")
            return 1
    else:
        print(f"fase/lista desconocida: {args.target}", file=sys.stderr)
        print(f"opciones: {', '.join(sorted([*PHASE_FNS, *SPEC_LISTS]))}", file=sys.stderr)
        return 2
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("target", nargs="?", default="list", help="fase o lista a correr (o 'list')")
    parser.add_argument("--port", type=int, default=None, help="override de puerto para wait_port_free")
    parser.add_argument("--timeout", type=int, default=90, help="timeout en segundos para wait_llama")
    parser.add_argument("--no-cache", action="store_true", help="rebuild sin cache para build_up_pithagoras")
    args = parser.parse_args()

    if args.target == "list":
        print("Fases individuales:", ", ".join(sorted(PHASE_FNS)))
        print("Listas declarativas:", ", ".join(sorted(SPEC_LISTS)))
        return

    raise SystemExit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
