"""Forma de cada Lifecycle plan (ver GLOSSARY.md) contra el ``cfg`` del test:
qué unidades corre cada comando, en qué tandas y con qué failure policy, y
que un servicio con ``enabled=False`` en su sub-config queda afuera."""

import dataclasses

import pytest

from rinthel_tui.lifecycle import specs
from rinthel_tui.lifecycle.domain.phases import data_dir


def _disable(cfg, attr):
    sub = getattr(cfg, attr)
    return dataclasses.replace(cfg, **{attr: dataclasses.replace(sub, enabled=False)})


def _services(plan):
    return [unit.service for batch in plan.batches for unit in batch.units]


PLANS = {
    "boot": specs.boot_plan,
    "terminate": specs.terminate_plan,
    "reload": specs.reload_plan,
    "install": specs.install_plan,
}


@pytest.mark.parametrize(
    ("plan", "disabled"),
    [
        ("boot", "understory"), ("boot", "pithagoras"), ("terminate", "pithagoras"),
        ("reload", "understory"), ("install", "understory"), ("install", "pithagoras"),
    ],
)
def test_a_disabled_service_is_left_out_of_the_plan_and_nothing_else_changes(cfg, plan, disabled):
    build = PLANS[plan]

    assert disabled in _services(build(cfg))
    assert _services(build(_disable(cfg, disabled))) == [s for s in _services(build(cfg)) if s != disabled]


def _shape(plan: specs.Plan) -> list[tuple[str | None, str, list[str]]]:
    return [
        (batch.marker, unit.service, [phase.label for phase in unit.phases])
        for batch in plan.batches
        for unit in batch.units
    ]


def test_boot_plan_checks_docker_then_spawns_llama_then_ups_each_docker_service(cfg):
    plan = specs.boot_plan(cfg)

    assert plan.on_failure == "stop"
    assert _shape(plan) == [
        (None, "docker", ["◈ DOCKER"]),
        (None, "llama-server", ["◈ LLAMA-SERVER", "◈ ESPERANDO LLAMA-SERVER"]),
        (None, "understory", ["◈ UNDERSTORY  --  MCP MEMORY LAYER", "◈ ESPERANDO UNDERSTORY"]),
        (None, "pithagoras", [
            "◈ DATOS DEL PORTAL  --  DUEÑO DEL DIRECTORIO",
            "◈ PORTAL  --  LOCAL MODEL ACTIVO",
            "◈ PITHAGORAS  --  PI TASK PORTAL",
            "◈ ESPERANDO PITHAGORAS",
        ]),
        (None, "deck", [
            "◈ DATOS DE DECK  --  DUEÑO DEL DIRECTORIO",
            "◈ DECK  --  WEB PORTAL",
            "◈ ESPERANDO DECK",
        ]),
    ]


def test_a_disabled_llama_server_is_neither_spawned_nor_awaited_on_reload(cfg):
    services = _services(specs.reload_plan(_disable(cfg, "llama")))

    assert "llama-server" not in services


def test_terminate_plan_stops_every_service_and_continues_on_failure(cfg):
    plan = specs.terminate_plan(cfg)

    assert plan.on_failure == "continue"
    assert _shape(plan) == [
        (None, "llama-server", ["◈ LLAMA-SERVER  --  LOCAL MODEL"]),
        (None, "understory", ["◈ UNDERSTORY  --  MCP MEMORY LAYER"]),
        (None, "pithagoras", ["◈ PITHAGORAS  --  PI TASK PORTAL"]),
        (None, "deck", ["◈ DECK  --  WEB PORTAL"]),
    ]


def test_reload_plan_shuts_down_then_boots_local_then_rebuilds_docker(cfg):
    plan = specs.reload_plan(cfg)

    assert plan.on_failure == "stop"
    assert _shape(plan) == [
        (None, "llama-server", ["◈ LLAMA-SERVER  --  LOCAL MODEL"]),
        (None, "understory", ["◈ UNDERSTORY  --  MCP MEMORY LAYER"]),
        (None, "pithagoras", ["◈ PITHAGORAS  --  PI TASK PORTAL"]),
        (None, "deck", ["◈ DECK  --  WEB PORTAL"]),
        (None, "llama-server", ["◈ PUERTO LLAMA-SERVER LIBRE"]),
        ("boot", "docker", ["◈ DOCKER"]),
        ("boot", "llama-server", ["◈ LLAMA-SERVER", "◈ ESPERANDO LLAMA-SERVER"]),
        ("rebuild", "understory", ["◈ UNDERSTORY  --  MCP MEMORY LAYER", "◈ ESPERANDO UNDERSTORY"]),
        ("rebuild", "pithagoras", [
            "◈ DATOS DEL PORTAL  --  DUEÑO DEL DIRECTORIO",
            "◈ PORTAL  --  LOCAL MODEL ACTIVO",
            "◈ PITHAGORAS  --  PI TASK PORTAL",
            "◈ ESPERANDO PITHAGORAS",
        ]),
        ("rebuild", "deck", [
            "◈ DATOS DE DECK  --  DUEÑO DEL DIRECTORIO",
            "◈ DECK  --  WEB PORTAL",
            "◈ ESPERANDO DECK",
        ]),
    ]
    rebuild = next(batch for batch in plan.batches if batch.marker == "rebuild")
    assert all(any(phase.kwargs.get("rebuild") is True for phase in unit.phases) for unit in rebuild.units)


def test_install_plan_preflight_first_then_every_unit_and_stops_on_failure(cfg):
    plan = specs.install_plan(cfg)

    assert plan.on_failure == "stop"
    assert _shape(plan) == [
        (None, "preflight", ["◈ PREFLIGHT — GPU/CUDA/cmake/docker"]),
        (None, "llama.cpp + modelo", [
            "◈ LLAMA.CPP — clone", "◈ LLAMA.CPP — build CUDA (native)", "◈ MODELO GGUF — descarga",
            "◈ LOCAL MODELS — catálogo inicial",
        ]),
        (None, "instance", ["◈ INSTANCE — secretos del .env"]),
        (None, "identity", ["◈ IDENTITY — rinthel.db + primer admin"]),
        (None, "deck", ["◈ DECK — SOUL de la Instance"]),
        (None, "pithagoras", ["◈ PITHAGORAS — clone + configurar"]),
        (None, "understory", ["◈ UNDERSTORY — scaffold + configurar"]),
    ]


def _portal_data_phase(plan: specs.Plan) -> specs.PhaseSpec:
    portal = next(unit for batch in plan.batches for unit in batch.units if unit.service == "pithagoras")
    return portal.phases[0]


def test_the_portal_data_directory_is_prepared_for_the_container_user_of_the_env(cfg):
    cfg.instance.env_path.write_text("PUID=1234\nPGID=5678\n")

    phase = _portal_data_phase(specs.boot_plan(cfg))

    assert phase.fn is data_dir.phase_ensure_data_dir
    assert phase.kwargs == {"path": cfg.instance.root / "data" / "pithagoras", "uid": 1234, "gid": 5678}


def test_decks_data_directory_is_its_volume_prepared_for_the_container_user(cfg):
    cfg.instance.env_path.write_text("PUID=1234\nPGID=5678\n")

    deck = next(unit for batch in specs.boot_plan(cfg).batches for unit in batch.units if unit.service == "deck")

    assert deck.phases[0].fn is data_dir.phase_ensure_data_dir
    assert deck.phases[0].kwargs == {"path": cfg.instance.root / "data" / "deck", "uid": 1234, "gid": 5678}


def test_the_portal_data_directory_defaults_to_the_compose_default_user(cfg):
    phase = _portal_data_phase(specs.boot_plan(cfg))

    assert (phase.kwargs["uid"], phase.kwargs["gid"]) == (1000, 1000)
