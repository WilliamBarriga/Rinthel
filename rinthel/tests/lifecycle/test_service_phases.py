"""Motor genérico de servicio gestionado — spawn/wait/kill (procesos locales)
y up/wait/down (docker compose), parametrizado sobre las instancias
reales de ``services.py``.

Las phases corren contra un ``Host`` de dobles (``fake_host``) y con un
``ManualClock``: se afirma sobre el resultado y las intenciones (un proceso
vivo, ``compose.up(service)``, una fase fallida con su causa), no sobre cómo
se llega ahí (ADR 0005). Los timeouts y el SIGKILL corren sin esperar.
"""

import dataclasses
from datetime import timedelta
from itertools import pairwise
from pathlib import Path

import pytest

from rinthel_tui.clock import ManualClock
from rinthel_tui.config import with_local_model
from rinthel_tui.lifecycle import services
from rinthel_tui.lifecycle.domain.errors import PhaseError
from rinthel_tui.lifecycle.domain.phases import service_phases
from rinthel_tui.lifecycle.domain.types import ProcessHandle
from rinthel_tui.models.domain.types import LocalModel
from tests.lifecycle.fakes import FakeProcesses, FakeRegistry, fake_host

LOCAL_SERVICES = services.LOCAL_SERVICES
DOCKER_SERVICES = services.DOCKER_SERVICES

MAX_LOG_BYTES = 10 * 1024 * 1024  # el tope que documenta ``phase_spawn``


@pytest.fixture
def cfg(cfg, tmp_path):
    """Every local service enabled: voice with its Local models active."""
    cfg = with_local_model(cfg, LocalModel("stt", "Stt", "stt", tmp_path / "ggml.bin", 0))
    return with_local_model(cfg, LocalModel("tts", "Tts", "tts", tmp_path / "tts.gguf", 0))


def _ids(services_list):
    return [s.display_name for s in services_list]


def _with_dir(service, directory):
    return dataclasses.replace(service, dir_of=lambda cfg: directory)


def _elapsed(clock: ManualClock, since) -> float:
    return (clock.now() - since) / timedelta(seconds=1)


def _signals(host) -> list[str]:
    """Las señales que ``phase_kill`` le mandó a quien escucha en el puerto, en orden."""
    return ["KILL" if event[2] else "TERM" for event in host.processes.log if event[0] == "stop_listeners"]


def _npm(versions: dict[str, str]) -> FakeRegistry:
    return FakeRegistry(versions)


# Deck con una imagen que recibe la última versión publicada de pi al reconstruirse.
_PI_PORTAL = dataclasses.replace(
    services.DECK_SERVICE, npm_build_args=(("PI_VERSION", "@earendil-works/pi-coding-agent"),)
)


# ── phase_spawn (proceso local) ─────────────────────────────────────────


@pytest.mark.parametrize("service", LOCAL_SERVICES, ids=_ids(LOCAL_SERVICES))
async def test_spawn_skips_when_the_port_is_already_taken(cfg, report, service):
    host, _ = fake_host()
    host.probe.script_port(service.port_of(cfg), True)

    await service_phases.phase_spawn(host, report, service=service.spec(cfg))

    assert host.processes.spawns == []
    assert len(report.warnings) == 1


@pytest.mark.parametrize("service", LOCAL_SERVICES, ids=_ids(LOCAL_SERVICES))
async def test_spawn_leaves_the_service_running_with_its_own_argv_and_log(cfg, report, service):
    host, _ = fake_host()

    await service_phases.phase_spawn(host, report, service=service.spec(cfg))

    (spawn,) = host.processes.spawns
    assert host.processes.is_alive(spawn.handle)
    assert list(spawn.argv) == service.build_argv(cfg)
    assert spawn.log == service.log_of(cfg)
    assert len(report.successes) == 1 and report.errors == []


@pytest.mark.parametrize("service", LOCAL_SERVICES, ids=_ids(LOCAL_SERVICES))
async def test_spawn_fails_the_phase_when_the_process_dies_right_away(cfg, report, service):
    host, _ = fake_host()
    host.processes.script(service.build_argv(cfg), exits=True)

    with pytest.raises(PhaseError):
        await service_phases.phase_spawn(host, report, service=service.spec(cfg))

    assert len(report.errors) == 1


@pytest.mark.parametrize("service", LOCAL_SERVICES, ids=_ids(LOCAL_SERVICES))
async def test_spawn_fails_the_phase_when_the_binary_does_not_start(cfg, report, service):
    host, _ = fake_host()
    host.processes.script(service.build_argv(cfg), missing=True)

    with pytest.raises(PhaseError):
        await service_phases.phase_spawn(host, report, service=service.spec(cfg))

    assert len(report.errors) == 1


async def test_spawn_gives_the_process_a_moment_to_crash_before_calling_it_launched(cfg, report):
    host, _ = fake_host()
    started = host.clock.now()

    await service_phases.phase_spawn(host, report, service=services.LLAMA_SERVICE.spec(cfg))

    assert _elapsed(host.clock, started) > 0


async def test_spawn_hands_the_service_env_to_the_process(cfg, report):
    host, _ = fake_host()
    service = dataclasses.replace(services.LLAMA_SERVICE, env_of=lambda c: {"CUDA_VISIBLE_DEVICES": "0"})

    await service_phases.phase_spawn(host, report, service=service.spec(cfg))

    (spawn,) = host.processes.spawns
    assert spawn.env == {"CUDA_VISIBLE_DEVICES": "0"}


class _InspectingProcesses(FakeProcesses):
    """Anota, al lanzar, cuáles de ``watch`` ya existen en disco."""

    def __init__(self, watch: list[Path]) -> None:
        super().__init__()
        self._watch = watch
        self.existed_at_launch: dict[Path, bool] = {}

    async def spawn(self, argv, *, log, cwd=None, env=None) -> int:
        self.existed_at_launch = {path: path.exists() for path in self._watch}
        return await super().spawn(argv, log=log, cwd=cwd, env=env)


async def test_spawn_writes_the_files_and_dirs_the_service_reads_before_launching_it(cfg, report):
    config_file = cfg.instance.data_dir / "server.json"
    slots = cfg.instance.data_dir / "slots"
    service = dataclasses.replace(
        services.LLAMA_SERVICE, files_of=lambda c: {config_file: "{}"}, dirs_of=lambda c: [slots]
    )
    host, _ = fake_host(processes=_InspectingProcesses([config_file, slots]))

    await service_phases.phase_spawn(host, report, service=service.spec(cfg))

    assert host.processes.existed_at_launch == {config_file: True, slots: True}


@pytest.mark.parametrize("service", LOCAL_SERVICES, ids=_ids(LOCAL_SERVICES))
async def test_spawn_rotates_an_oversized_log_keeping_one_backup(cfg, report, service):
    host, _ = fake_host()
    log = service.log_of(cfg)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_bytes(b"x" * (MAX_LOG_BYTES + 1))
    backup = log.with_name(log.name + ".1")
    backup.write_bytes(b"old backup")

    await service_phases.phase_spawn(host, report, service=service.spec(cfg))

    assert backup.stat().st_size == MAX_LOG_BYTES + 1
    assert not log.exists() or log.stat().st_size == 0


async def test_spawn_keeps_a_small_log_as_it_is(cfg, report):
    host, _ = fake_host()
    service = services.LLAMA_SERVICE
    log = service.log_of(cfg)
    log.write_bytes(b"x" * 100)

    await service_phases.phase_spawn(host, report, service=service.spec(cfg))

    assert log.read_bytes() == b"x" * 100
    assert not log.with_name(log.name + ".1").exists()


# ── phase_wait_ready ──────────────────────────────────────────────────────


@pytest.mark.parametrize("service", LOCAL_SERVICES + DOCKER_SERVICES, ids=_ids(LOCAL_SERVICES + DOCKER_SERVICES))
async def test_wait_ready_succeeds_when_the_service_answers(cfg, report, service):
    host, _ = fake_host()
    host.probe.script_http(service.ready_url_of(cfg), True)

    assert await service_phases.phase_wait_ready(host, report, service=service.spec(cfg)) is True

    assert len(report.successes) == 1 and report.warnings == []


@pytest.mark.parametrize("service", LOCAL_SERVICES + DOCKER_SERVICES, ids=_ids(LOCAL_SERVICES + DOCKER_SERVICES))
async def test_wait_ready_only_warns_when_the_service_never_answers(cfg, report, service):
    host, _ = fake_host()

    assert await service_phases.phase_wait_ready(host, report, service=service.spec(cfg), timeout=0) is False

    assert len(report.warnings) == 1 and report.errors == []


async def test_wait_ready_timeout_hint_only_fires_when_configured(cfg, report):
    host, _ = fake_host()

    await service_phases.phase_wait_ready(host, report, service=services.LLAMA_SERVICE.spec(cfg), timeout=0)
    assert len(report.infos) == 1

    quiet = type(report)()
    await service_phases.phase_wait_ready(host, quiet, service=services.UNDERSTORY_SERVICE.spec(cfg), timeout=0)
    assert quiet.infos == []


async def test_wait_ready_is_a_noop_for_a_service_without_a_ready_url(cfg, report):
    host, log = fake_host()
    service = dataclasses.replace(services.UNDERSTORY_SERVICE, ready_url_of=None)

    assert await service_phases.phase_wait_ready(host, report, service=service.spec(cfg)) is True

    assert (report.infos, report.successes, report.warnings, report.errors) == ([], [], [], []) and log == []


async def test_wait_ready_backoff_grows_and_caps(cfg, report):
    host, _ = fake_host()
    service = dataclasses.replace(
        services.LLAMA_SERVICE, ready_poll_interval=2.0, ready_poll_backoff=2.0, ready_poll_max_interval=6.0
    )
    started = host.clock.now()

    await service_phases.phase_wait_ready(host, report, service=service.spec(cfg), timeout=20)

    asked = host.probe.http_asked_at
    gaps = [(later - earlier) / timedelta(seconds=1) for earlier, later in pairwise(asked)]
    # 2 -> 4 -> 6 (cap) -> 6 -> lo que quede del timeout
    assert gaps == [2.0, 4.0, 6.0, 6.0, 2.0]
    assert _elapsed(host.clock, started) == 20


async def test_wait_ready_never_waits_past_its_timeout(cfg, report):
    host, _ = fake_host()
    service = dataclasses.replace(
        services.UNDERSTORY_SERVICE, ready_poll_interval=2.0, ready_poll_backoff=3.0, ready_poll_max_interval=100.0
    )
    started = host.clock.now()

    await service_phases.phase_wait_ready(host, report, service=service.spec(cfg), timeout=5)

    assert _elapsed(host.clock, started) == 5.0
    assert len(report.warnings) == 1


async def test_wait_ready_stops_polling_as_soon_as_the_service_answers(cfg, report):
    host, _ = fake_host()
    service = dataclasses.replace(
        services.DECK_SERVICE, ready_poll_interval=1.0, ready_poll_backoff=2.0, ready_poll_max_interval=10.0
    )
    host.probe.script_http(service.ready_url_of(cfg), [False, False, True])
    started = host.clock.now()

    assert await service_phases.phase_wait_ready(host, report, service=service.spec(cfg), timeout=30) is True

    assert _elapsed(host.clock, started) == 3.0  # esperó 1 s y 2 s, y no más


async def test_a_required_wait_ready_fails_the_phase_on_timeout(cfg, report):
    host, _ = fake_host()

    with pytest.raises(PhaseError):
        await service_phases.phase_wait_ready(
            host, report, service=services.LLAMA_SERVICE.spec(cfg), timeout=0, required=True
        )

    assert len(report.errors) == 1


# ── phase_kill (proceso local) ────────────────────────────────────────────


@pytest.mark.parametrize("service", LOCAL_SERVICES, ids=_ids(LOCAL_SERVICES))
async def test_kill_only_warns_when_the_service_was_not_running(cfg, report, service):
    host, _ = fake_host()

    await service_phases.phase_kill(host, report, service=service.spec(cfg))

    assert len(report.warnings) == 1 and _signals(host) == []


@pytest.mark.parametrize("service", LOCAL_SERVICES, ids=_ids(LOCAL_SERVICES))
async def test_kill_stops_the_service_with_a_term(cfg, report, service):
    host, _ = fake_host()
    host.probe.script_port(service.port_of(cfg), [True, False])
    host.processes.listen(service.port_of(cfg), ProcessHandle(4242))

    await service_phases.phase_kill(host, report, service=service.spec(cfg))

    assert len(report.successes) == 1 and _signals(host) == ["TERM"]
    assert report.warnings == []


async def test_kill_warns_when_it_cannot_identify_the_listener_but_still_waits_and_forces(cfg, report):
    host, _ = fake_host()
    port = services.LLAMA_SERVICE.port_of(cfg)
    host.probe.script_port(port, [True, False])

    await service_phases.phase_kill(host, report, service=services.LLAMA_SERVICE.spec(cfg))

    assert _signals(host) == ["TERM"]
    assert len(report.warnings) == 1 and len(report.successes) == 1


async def test_kill_falls_back_to_sigkill_after_ten_seconds_of_term(cfg, report):
    host, _ = fake_host()
    port = services.LLAMA_SERVICE.port_of(cfg)
    host.probe.script_port(port, [True] * 11 + [False])  # corriendo, TERM sin efecto, cae con el KILL
    started = host.clock.now()

    await service_phases.phase_kill(host, report, service=services.LLAMA_SERVICE.spec(cfg))

    assert _signals(host) == ["TERM", "KILL"]
    assert _elapsed(host.clock, started) == 10
    assert len(report.successes) == 1 and report.errors == []


async def test_kill_warns_when_the_port_stays_busy_after_sigkill(cfg, report):
    host, _ = fake_host()
    host.probe.script_port(services.LLAMA_SERVICE.port_of(cfg), True)
    host.processes.listen(services.LLAMA_SERVICE.port_of(cfg), ProcessHandle(4242))

    await service_phases.phase_kill(host, report, service=services.LLAMA_SERVICE.spec(cfg))

    assert _signals(host) == ["TERM", "KILL"]
    assert len(report.warnings) == 1 and report.errors == []


async def test_a_required_kill_fails_the_phase_when_the_port_stays_busy_after_sigkill(cfg, report):
    host, _ = fake_host()
    host.probe.script_port(services.LLAMA_SERVICE.port_of(cfg), True)

    with pytest.raises(PhaseError):
        await service_phases.phase_kill(host, report, service=services.LLAMA_SERVICE.spec(cfg), required=True)

    assert len(report.errors) == 1


# ── enabled_of ─────────────────────────────────────────────────────────────


def test_enabled_of_defaults_to_true(cfg):
    assert dataclasses.replace(services.LLAMA_SERVICE).enabled_of(cfg) is True


@pytest.mark.parametrize("service", LOCAL_SERVICES + DOCKER_SERVICES, ids=_ids(LOCAL_SERVICES + DOCKER_SERVICES))
def test_enabled_of_resolves_against_real_config(cfg, service):
    assert service.enabled_of(cfg) is True


def test_enabled_of_custom_resolves_against_cfg(cfg):
    service = dataclasses.replace(
        services.UNDERSTORY_SERVICE, enabled_of=lambda c: c.understory.port == cfg.understory.port
    )
    assert service.enabled_of(cfg) is True
    disabled_cfg = dataclasses.replace(cfg, understory=dataclasses.replace(cfg.understory, port=0))
    assert service.enabled_of(disabled_cfg) is False


# ── phase_wait_port_free (genérico, usado en RELOAD) ────────────────────


async def test_wait_port_free_succeeds_immediately_when_nobody_listens(cfg, report):
    host, _ = fake_host()

    await service_phases.phase_wait_port_free(host, report, port=1234)

    assert len(report.successes) == 1 and report.warnings == []


async def test_wait_port_free_waits_until_the_port_is_released(cfg, report):
    host, _ = fake_host()
    host.probe.script_port(1234, [True, True, False])
    started = host.clock.now()

    await service_phases.phase_wait_port_free(host, report, port=1234)

    assert _elapsed(host.clock, started) == 2
    assert len(report.successes) == 1


async def test_wait_port_free_warns_and_goes_on_after_the_timeout(cfg, report):
    host, _ = fake_host()
    host.probe.script_port(1234, True)
    started = host.clock.now()

    await service_phases.phase_wait_port_free(host, report, port=1234, timeout=30)

    assert _elapsed(host.clock, started) == 30
    assert len(report.warnings) == 1 and report.errors == []


# ── phase_up / phase_down (docker compose) ───────────────────────────────


@pytest.mark.parametrize("service", DOCKER_SERVICES, ids=_ids(DOCKER_SERVICES))
async def test_up_and_down_skip_when_the_stack_directory_is_missing(cfg, report, tmp_path, service):
    host, _ = fake_host()
    service = _with_dir(service, tmp_path / "no-existe")

    await service_phases.phase_up(host, report, service=service.spec(cfg))
    await service_phases.phase_down(host, report, service=service.spec(cfg))

    assert host.compose.calls == [] and len(report.warnings) == 2


@pytest.mark.parametrize("service", DOCKER_SERVICES, ids=_ids(DOCKER_SERVICES))
async def test_up_brings_the_service_up(cfg, report, tmp_path, service):
    host, _ = fake_host()
    service = _with_dir(service, tmp_path)

    await service_phases.phase_up(host, report, service=service.spec(cfg))

    assert service.compose_service_name in host.compose.running
    assert len(report.successes) == 1 and report.errors == []


@pytest.mark.parametrize("service", DOCKER_SERVICES, ids=_ids(DOCKER_SERVICES))
async def test_up_fails_the_phase_when_compose_up_fails(cfg, report, tmp_path, service):
    host, _ = fake_host()
    service = _with_dir(service, tmp_path)
    host.compose.fail_rc("up", 1, "boom")

    with pytest.raises(PhaseError):
        await service_phases.phase_up(host, report, service=service.spec(cfg))

    assert service.compose_service_name not in host.compose.running
    assert len(report.errors) == 1


async def test_up_with_rebuild_builds_with_the_latest_npm_version(cfg, report, tmp_path):
    # Con el cache de Docker prendido, el build arg con la última versión de pi
    # es lo que rehace su capa cuando sale una nueva.
    host, _ = fake_host(registry=_npm({"@earendil-works/pi-coding-agent": "1.2.3"}))
    service = _with_dir(_PI_PORTAL, tmp_path)

    await service_phases.phase_up(host, report, service=service.spec(cfg), rebuild=True)

    (up,) = [c for c in host.compose.calls if c[0] == "up"]
    assert up[1:3] == ("deck", {"PI_VERSION": "1.2.3"})


async def test_up_with_rebuild_still_builds_with_latest_when_the_registry_is_unreachable(cfg, report, tmp_path):
    # Con "latest" la capa de pi sale del cache: no se actualiza, pero el reload no se corta.
    host, _ = fake_host(registry=_npm({}))
    service = _with_dir(_PI_PORTAL, tmp_path)

    await service_phases.phase_up(host, report, service=service.spec(cfg), rebuild=True)

    (up,) = [c for c in host.compose.calls if c[0] == "up"]
    assert up[2] == {"PI_VERSION": "latest"}
    assert len(report.successes) == 1 and report.errors == []


async def test_up_with_rebuild_rebuilds_a_service_with_no_npm_build_args(cfg, report, tmp_path):
    host, _ = fake_host()
    service = _with_dir(services.DECK_SERVICE, tmp_path)

    await service_phases.phase_up(host, report, service=service.spec(cfg), rebuild=True)

    (up,) = [c for c in host.compose.calls if c[0] == "up"]
    assert up[2] == {}


async def test_up_with_rebuild_does_not_build_a_service_that_has_no_build(cfg, report, tmp_path):
    host, _ = fake_host()
    service = _with_dir(services.UNDERSTORY_SERVICE, tmp_path)

    await service_phases.phase_up(host, report, service=service.spec(cfg), rebuild=True)

    (up,) = [c for c in host.compose.calls if c[0] == "up"]
    assert up[2] is None


async def test_up_fails_the_phase_when_the_rebuild_fails(cfg, report, tmp_path):
    host, _ = fake_host(registry=_npm({"@earendil-works/pi-coding-agent": "1.2.3"}))
    service = _with_dir(_PI_PORTAL, tmp_path)
    host.compose.fail_rc("up", 1, "build failed")

    with pytest.raises(PhaseError):
        await service_phases.phase_up(host, report, service=service.spec(cfg), rebuild=True)

    assert "portal" not in host.compose.running and len(report.errors) == 1


@pytest.mark.parametrize("service", DOCKER_SERVICES, ids=_ids(DOCKER_SERVICES))
async def test_down_takes_only_its_own_service_down(cfg, report, tmp_path, service):
    host, _ = fake_host()
    service = _with_dir(service, tmp_path)
    host.compose.running.update({service.compose_service_name, "neighbour"})

    await service_phases.phase_down(host, report, service=service.spec(cfg))

    assert host.compose.running == {"neighbour"}
    assert len(report.successes) == 1


@pytest.mark.parametrize("service", DOCKER_SERVICES, ids=_ids(DOCKER_SERVICES))
async def test_down_fails_the_phase_when_compose_down_fails(cfg, report, tmp_path, service):
    host, _ = fake_host()
    service = _with_dir(service, tmp_path)
    host.compose.fail_rc("down", 1, "boom")

    with pytest.raises(PhaseError):
        await service_phases.phase_down(host, report, service=service.spec(cfg))

    assert len(report.errors) == 1
