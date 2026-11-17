"""Forma de cada Lifecycle plan (ver GLOSSARY.md) contra el ``cfg`` del test:
qué unidades corre cada comando, en qué tandas y con qué failure policy, y
que un servicio con ``enabled=False`` en su sub-config queda afuera."""

import dataclasses

import pytest

from rinthel_tui.config import with_local_model
from rinthel_tui.lifecycle import services, specs
from rinthel_tui.lifecycle.domain.phases import data_dir, managed_service
from rinthel_tui.models.domain.types import LocalModel


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
        ("boot", "understory"), ("boot", "deck"), ("terminate", "deck"),
        ("reload", "understory"), ("install", "understory"), ("install", "deck"),
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


def test_boot_plan_checks_docker_then_spawns_the_local_services_then_ups_each_docker_service(cfg):
    plan = specs.boot_plan(cfg)

    assert plan.on_failure == "stop"
    assert _shape(plan) == [
        (None, "docker", ["◈ DOCKER"]),
        (None, "llama-server", ["◈ LLAMA-SERVER", "◈ ESPERANDO LLAMA-SERVER"]),
        (None, "hostexecd", ["◈ HOSTEXECD  --  HOST EXEC", "◈ ESPERANDO HOSTEXECD"]),
        (None, "understory", ["◈ UNDERSTORY  --  MCP MEMORY LAYER", "◈ ESPERANDO UNDERSTORY"]),
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
        (None, "hostexecd", ["◈ HOSTEXECD  --  HOST EXEC"]),
        (None, "understory", ["◈ UNDERSTORY  --  MCP MEMORY LAYER"]),
        (None, "deck", ["◈ DECK  --  WEB PORTAL"]),
    ]


def test_reload_plan_shuts_down_then_boots_local_then_rebuilds_docker(cfg):
    plan = specs.reload_plan(cfg)

    assert plan.on_failure == "stop"
    assert _shape(plan) == [
        (None, "llama-server", ["◈ LLAMA-SERVER  --  LOCAL MODEL"]),
        (None, "hostexecd", ["◈ HOSTEXECD  --  HOST EXEC"]),
        (None, "understory", ["◈ UNDERSTORY  --  MCP MEMORY LAYER"]),
        (None, "deck", ["◈ DECK  --  WEB PORTAL"]),
        (None, "llama-server", ["◈ PUERTO LLAMA-SERVER LIBRE"]),
        ("boot", "docker", ["◈ DOCKER"]),
        ("boot", "llama-server", ["◈ LLAMA-SERVER", "◈ ESPERANDO LLAMA-SERVER"]),
        ("boot", "hostexecd", ["◈ HOSTEXECD  --  HOST EXEC", "◈ ESPERANDO HOSTEXECD"]),
        ("rebuild", "understory", ["◈ UNDERSTORY  --  MCP MEMORY LAYER", "◈ ESPERANDO UNDERSTORY"]),
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
        (None, "instance", [
            "◈ INSTANCE — secretos del .env", "◈ INSTANCE — token de host exec",
            "◈ INSTANCE — usuario de los contenedores", "◈ INSTANCE — compose de la Platform",
        ]),
        (None, "identity", ["◈ IDENTITY — rinthel.db + primer admin"]),
        (None, "deck", ["◈ DECK — SOUL de la Instance"]),
        (None, "understory", ["◈ UNDERSTORY — token + bundle"]),
    ]


def _voiced(cfg, tmp_path):
    cfg = with_local_model(cfg, LocalModel("w", "W", "stt", tmp_path / "ggml.bin", 0))
    return with_local_model(cfg, LocalModel("p", "P", "tts", tmp_path / "p.gguf", 0))


def test_an_active_voice_key_boots_and_terminates_its_service_and_none_without_it(cfg, tmp_path):
    voiced = _voiced(cfg, tmp_path)

    assert _shape(specs.boot_plan(voiced))[1:4] == [
        (None, "llama-server", ["◈ LLAMA-SERVER", "◈ ESPERANDO LLAMA-SERVER"]),
        (None, "whisper-server", ["◈ WHISPER-SERVER  --  STT", "◈ ESPERANDO WHISPER-SERVER"]),
        (None, "audiocpp-server", ["◈ AUDIOCPP-SERVER  --  TTS", "◈ ESPERANDO AUDIOCPP-SERVER"]),
    ]
    assert {"whisper-server", "audiocpp-server"} <= set(_services(specs.terminate_plan(voiced)))
    for build in (specs.boot_plan, specs.terminate_plan, specs.reload_plan):
        assert not {"whisper-server", "audiocpp-server"} & set(_services(build(cfg)))


def test_install_with_voice_adds_the_voice_unit_last(cfg):
    plan = specs.install_plan(cfg, voice=True)

    assert _shape(plan)[:-1] == _shape(specs.install_plan(cfg))
    assert _shape(plan)[-1] == (None, "voz", [
        "◈ WHISPER.CPP — clone + build CPU", "◈ WHISPER — modelo ggml-base",
        "◈ AUDIO.CPP — clone + build CUDA", "◈ POCKET-TTS — GGUF español",
        "◈ VOZ — catálogo y Local models activos", "◈ VOZ — arrancar stt/tts",
    ])


def test_install_with_voice_on_windows_skips_it_with_a_notice(cfg):
    plan = specs.install_plan(dataclasses.replace(cfg, platform="windows"), voice=True)

    (voice,) = [unit for batch in plan.batches for unit in batch.units if unit.service == "voz"]
    assert [phase.fn for phase in voice.phases] == [managed_service.phase_notice]


@pytest.mark.parametrize("service", ["llama-server", "whisper-server", "audiocpp-server"])
def test_a_model_switch_restarts_only_its_service_and_every_step_is_required(cfg, tmp_path, service):
    definition = next(s for s in services.MODEL_SERVICES.values() if s.display_name == service)

    restart = specs.restart_plan(_voiced(cfg, tmp_path), definition)
    stop = specs.stop_plan(_voiced(cfg, tmp_path), definition)

    (unit,) = restart.batches[0].units
    assert unit.service == service
    assert [phase.fn for phase in unit.phases] == [
        managed_service.phase_kill, managed_service.phase_spawn, managed_service.phase_wait_ready,
    ]
    assert unit.phases[0].kwargs["required"] and unit.phases[2].kwargs["required"]
    ((stopping,),) = [batch.units for batch in stop.batches]
    assert [(p.fn, p.kwargs["required"]) for p in stopping.phases] == [(managed_service.phase_kill, True)]


def _deck_data_phase(plan: specs.Plan) -> specs.PhaseSpec:
    deck = next(unit for batch in plan.batches for unit in batch.units if unit.service == "deck")
    return deck.phases[0]


def test_decks_data_directory_is_its_volume_prepared_for_the_container_user(cfg):
    cfg.instance.env_path.write_text("PUID=1234\nPGID=5678\n")

    deck = next(unit for batch in specs.boot_plan(cfg).batches for unit in batch.units if unit.service == "deck")

    assert deck.phases[0].fn is data_dir.phase_ensure_data_dir
    assert deck.phases[0].kwargs == {"path": cfg.instance.root / "data" / "deck", "uid": 1234, "gid": 5678}


def test_decks_data_directory_defaults_to_the_compose_default_user(cfg):
    phase = _deck_data_phase(specs.boot_plan(cfg))

    assert (phase.kwargs["uid"], phase.kwargs["gid"]) == (1000, 1000)
