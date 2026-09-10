"""Motor genérico de servicio gestionado — spawn/wait/kill (procesos
locales) y up/wait/down (docker compose), parametrizado sobre las
instancias reales de ``services.py`` en vez de una función por servicio.

Estilo de mocking: igual que en el test_phases.py original — se parchea
``_port_in_use``/``_http_ok``/``_run``/``_docker_compose`` sobre el módulo
``managed_service`` y ``asyncio.create_subprocess_exec`` sobre ``asyncio``.
Los casos "spawn exitoso" esperan de verdad el timeout de 1.5s de la fase
(decisión ya tomada: fidelidad de comportamiento sobre velocidad); el caso
"necesita SIGKILL" del kill-loop (~10s reales) se prueba una sola vez, para
llama-server, no por cada servicio parametrizado.
"""

import asyncio
import dataclasses

import pytest

from rinthel_tui.lifecycle import managed_service, services
from rinthel_tui.lifecycle.types import PhaseError

LOCAL_SERVICES = services.LOCAL_SERVICES
DOCKER_SERVICES = services.DOCKER_SERVICES


def _ids(services_list):
    return [s.display_name for s in services_list]


class _FakeProc:
    def __init__(self, returncode: int | None = None, pid: int = 1234, hang: bool = False):
        self.returncode = returncode
        self.pid = pid
        self._hang = hang

    async def wait(self) -> int:
        if self._hang:
            await asyncio.sleep(10)
        return self.returncode


async def _coro(value):
    return value


def _port_sequence(values: list[bool]):
    it = iter(values)
    state = {"last": False}

    async def fake(port: int) -> bool:
        try:
            state["last"] = next(it)
        except StopIteration:
            pass
        return state["last"]

    return fake


async def _async_false(*args, **kwargs) -> bool:
    return False


async def _async_true(*args, **kwargs) -> bool:
    return True


async def _fake_run_ok(*args, **kwargs) -> int:
    return 0


def _recording_docker_compose(rc_by_first_arg: dict[str, int] | None = None):
    rc_by_first_arg = rc_by_first_arg or {}
    calls: list[list[str]] = []

    async def fake(args, cwd, report, extra_env=None):
        calls.append(list(args))
        return rc_by_first_arg.get(args[0], 0)

    return fake, calls


def _with_dir(service, directory):
    return dataclasses.replace(service, dir_of=lambda cfg: directory)


# ── phase_spawn / phase_wait_ready / phase_kill (proceso local) ─────────


@pytest.mark.parametrize("service", LOCAL_SERVICES, ids=_ids(LOCAL_SERVICES))
async def test_spawn_skips_when_port_busy(monkeypatch, cfg, report, service):
    monkeypatch.setattr(managed_service, "_port_in_use", _async_true)
    spawned = False

    async def fake_exec(*args, **kwargs):
        nonlocal spawned
        spawned = True
        return _FakeProc(0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    await managed_service.phase_spawn(cfg, report, service=service)
    assert not spawned
    assert any("no relanzo" in msg for msg in report.warnings)


@pytest.mark.parametrize("service", LOCAL_SERVICES, ids=_ids(LOCAL_SERVICES))
async def test_spawn_raises_when_process_dies_immediately(monkeypatch, cfg, report, service):
    monkeypatch.setattr(managed_service, "_port_in_use", _async_false)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", lambda *a, **k: _coro(_FakeProc(1)))
    try:
        await managed_service.phase_spawn(cfg, report, service=service)
        raised = False
    except PhaseError:
        raised = True
    assert raised
    assert any("murió al instante" in msg for msg in report.errors)


@pytest.mark.parametrize("service", LOCAL_SERVICES, ids=_ids(LOCAL_SERVICES))
async def test_spawn_succeeds_when_process_stays_alive(monkeypatch, cfg, report, service):
    monkeypatch.setattr(managed_service, "_port_in_use", _async_false)
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", lambda *a, **k: _coro(_FakeProc(0, hang=True))
    )
    await managed_service.phase_spawn(cfg, report, service=service)
    assert any("lanzado en background" in msg for msg in report.successes)


@pytest.mark.parametrize("service", LOCAL_SERVICES, ids=_ids(LOCAL_SERVICES))
async def test_wait_ready_succeeds(monkeypatch, cfg, report, service):
    monkeypatch.setattr(managed_service, "_http_ok", _async_true)
    await managed_service.phase_wait_ready(cfg, report, service=service)
    assert any("respondiendo" in msg for msg in report.successes)


@pytest.mark.parametrize("service", LOCAL_SERVICES, ids=_ids(LOCAL_SERVICES))
async def test_wait_ready_warns_on_timeout(monkeypatch, cfg, report, service):
    monkeypatch.setattr(managed_service, "_http_ok", _async_false)
    await managed_service.phase_wait_ready(cfg, report, service=service, timeout=0)
    assert any("nada respondiendo" in msg for msg in report.warnings)


async def test_wait_ready_timeout_hint_only_fires_when_configured(monkeypatch, cfg, report):
    monkeypatch.setattr(managed_service, "_http_ok", _async_false)
    await managed_service.phase_wait_ready(cfg, report, service=services.LLAMA_SERVICE, timeout=0)
    assert any("Levanta el modelo local" in msg for msg in report.infos)


async def test_wait_ready_no_hint_for_services_without_one(monkeypatch, cfg, report):
    monkeypatch.setattr(managed_service, "_http_ok", _async_false)
    await managed_service.phase_wait_ready(cfg, report, service=services.WHISPER_SERVICE, timeout=0)
    assert report.infos == []


# ── backoff exponencial del polling de wait_ready ─────────────────────────


def _recording_sleep():
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    return fake_sleep, slept


async def test_wait_ready_backoff_grows_and_caps(monkeypatch, cfg, report):
    monkeypatch.setattr(managed_service, "_http_ok", _async_false)
    fake_sleep, slept = _recording_sleep()
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    service = dataclasses.replace(
        services.LLAMA_SERVICE,
        ready_poll_interval=2.0,
        ready_poll_backoff=2.0,
        ready_poll_max_interval=6.0,
    )
    await managed_service.phase_wait_ready(cfg, report, service=service, timeout=20)
    # 2 -> 4 -> 6 (cap) -> 6 -> ... clampeado por lo que quede de timeout
    assert slept[:3] == [2.0, 4.0, 6.0]
    assert all(s <= 6.0 for s in slept)
    assert any("nada respondiendo" in msg for msg in report.warnings)


async def test_wait_ready_backoff_does_not_overshoot_timeout(monkeypatch, cfg, report):
    monkeypatch.setattr(managed_service, "_http_ok", _async_false)
    fake_sleep, slept = _recording_sleep()
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    service = dataclasses.replace(
        services.WHISPER_SERVICE,
        ready_poll_interval=2.0,
        ready_poll_backoff=3.0,
        ready_poll_max_interval=100.0,
    )
    await managed_service.phase_wait_ready(cfg, report, service=service, timeout=5)
    assert sum(slept) == 5.0
    assert slept[-1] <= 3.0


async def test_wait_ready_stops_polling_as_soon_as_it_responds(monkeypatch, cfg, report):
    fake_sleep, slept = _recording_sleep()
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(managed_service, "_http_ok", _port_sequence([False, False, True]))
    service = dataclasses.replace(
        services.TTS_SERVICE, ready_poll_interval=1.0, ready_poll_backoff=2.0, ready_poll_max_interval=10.0
    )
    await managed_service.phase_wait_ready(cfg, report, service=service, timeout=30)
    assert slept == [1.0, 2.0]
    assert any("respondiendo" in msg for msg in report.successes)


@pytest.mark.parametrize("service", LOCAL_SERVICES, ids=_ids(LOCAL_SERVICES))
async def test_kill_warns_when_not_running(monkeypatch, cfg, report, service):
    monkeypatch.setattr(managed_service, "_port_in_use", _async_false)
    await managed_service.phase_kill(cfg, report, service=service)
    assert any("No había" in msg for msg in report.warnings)


@pytest.mark.parametrize("service", LOCAL_SERVICES, ids=_ids(LOCAL_SERVICES))
async def test_kill_succeeds_after_term(monkeypatch, cfg, report, service):
    monkeypatch.setattr(managed_service, "_port_in_use", _port_sequence([True, False]))
    monkeypatch.setattr(managed_service, "_run", _fake_run_ok)
    await managed_service.phase_kill(cfg, report, service=service)
    assert any("parado en" in msg for msg in report.successes)


async def test_kill_falls_back_to_sigkill(monkeypatch, cfg, report):
    # 1 chequeo inicial + 10 en el loop del TERM (todas ocupado) + 1 final tras KILL.
    monkeypatch.setattr(managed_service, "_port_in_use", _port_sequence([True] * 11 + [False]))
    monkeypatch.setattr(managed_service, "_run", _fake_run_ok)
    await managed_service.phase_kill(cfg, report, service=services.LLAMA_SERVICE)
    assert any("SIGKILL" in msg for msg in report.successes)


# ── enabled_of ───────────────────────────────────────────────────────────


def test_enabled_of_defaults_to_true(cfg):
    service = dataclasses.replace(services.LLAMA_SERVICE)
    assert service.enabled_of(cfg) is True


@pytest.mark.parametrize("service", LOCAL_SERVICES + DOCKER_SERVICES, ids=_ids(LOCAL_SERVICES + DOCKER_SERVICES))
def test_enabled_of_resolves_against_real_config(cfg, service):
    assert service.enabled_of(cfg) is True


def test_enabled_of_custom_resolves_against_cfg(cfg):
    service = dataclasses.replace(services.WHISPER_SERVICE, enabled_of=lambda c: c.whisper.port == cfg.whisper.port)
    assert service.enabled_of(cfg) is True
    disabled_cfg = dataclasses.replace(cfg, whisper=dataclasses.replace(cfg.whisper, port=0))
    assert service.enabled_of(disabled_cfg) is False


# ── phase_wait_port_free (genérico, usado en RELOAD) ────────────────────


async def test_wait_port_free_succeeds_immediately(monkeypatch, cfg, report):
    monkeypatch.setattr(managed_service, "_port_in_use", _async_false)
    await managed_service.phase_wait_port_free(cfg, report, port_of=lambda cfg: 1234)
    assert any("libre" in msg for msg in report.successes)


async def test_wait_port_free_warns_after_timeout(monkeypatch, cfg, report):
    monkeypatch.setattr(managed_service, "_port_in_use", _async_true)
    await managed_service.phase_wait_port_free(cfg, report, port_of=lambda cfg: 1234, timeout=0)
    assert any("sigue ocupado" in msg for msg in report.warnings)


# ── phase_up / phase_wait_ready / phase_down (docker compose) ───────────
# phase_wait_ready es la misma función que se probó arriba para los
# servicios locales — acá solo se cubren los casos específicos de
# DockerComposeService (ready_url_of opcional).


@pytest.mark.parametrize("service", DOCKER_SERVICES, ids=_ids(DOCKER_SERVICES))
async def test_up_skips_when_dir_missing(cfg, report, tmp_path, service):
    service = _with_dir(service, tmp_path / "no-existe")
    await managed_service.phase_up(cfg, report, service=service)
    assert any("no encontrado" in msg for msg in report.warnings)


@pytest.mark.parametrize("service", DOCKER_SERVICES, ids=_ids(DOCKER_SERVICES))
async def test_up_succeeds(monkeypatch, cfg, report, tmp_path, service):
    service = _with_dir(service, tmp_path)
    fake, calls = _recording_docker_compose()
    monkeypatch.setattr(managed_service, "_docker_compose", fake)

    await managed_service.phase_up(cfg, report, service=service)

    assert calls[0] == ["up", "-d"]
    assert any("levantado" in msg for msg in report.successes)


@pytest.mark.parametrize("service", DOCKER_SERVICES, ids=_ids(DOCKER_SERVICES))
async def test_up_raises_when_compose_up_fails(monkeypatch, cfg, report, tmp_path, service):
    service = _with_dir(service, tmp_path)
    fake, calls = _recording_docker_compose({"up": 1})
    monkeypatch.setattr(managed_service, "_docker_compose", fake)

    try:
        await managed_service.phase_up(cfg, report, service=service)
        raised = False
    except PhaseError:
        raised = True

    assert raised
    assert any("docker compose up falló" in msg for msg in report.errors)


async def test_up_with_no_cache_rebuilds_first_when_service_supports_build(
    monkeypatch, cfg, report, tmp_path
):
    service = _with_dir(services.PITHAGORAS_SERVICE, tmp_path)
    fake, calls = _recording_docker_compose()
    monkeypatch.setattr(managed_service, "_docker_compose", fake)

    await managed_service.phase_up(cfg, report, service=service, no_cache=True)

    assert calls[0][:2] == ["build", "--no-cache"]


async def test_up_with_no_cache_is_noop_when_service_has_no_build_args(
    monkeypatch, cfg, report, tmp_path
):
    service = _with_dir(services.UNDERSTORY_SERVICE, tmp_path)
    fake, calls = _recording_docker_compose()
    monkeypatch.setattr(managed_service, "_docker_compose", fake)

    await managed_service.phase_up(cfg, report, service=service, no_cache=True)

    assert "build" not in [c[0] for c in calls]


async def test_up_raises_when_build_fails(monkeypatch, cfg, report, tmp_path):
    service = _with_dir(services.PITHAGORAS_SERVICE, tmp_path)
    fake, calls = _recording_docker_compose({"build": 1})
    monkeypatch.setattr(managed_service, "_docker_compose", fake)

    try:
        await managed_service.phase_up(cfg, report, service=service, no_cache=True)
        raised = False
    except PhaseError:
        raised = True

    assert raised
    assert any("docker compose build falló" in msg for msg in report.errors)


@pytest.mark.parametrize("service", DOCKER_SERVICES, ids=_ids(DOCKER_SERVICES))
async def test_wait_ready_docker_succeeds(monkeypatch, cfg, report, service):
    monkeypatch.setattr(managed_service, "_http_ok", _async_true)
    await managed_service.phase_wait_ready(cfg, report, service=service)
    assert any("respondiendo" in msg for msg in report.successes)


@pytest.mark.parametrize("service", DOCKER_SERVICES, ids=_ids(DOCKER_SERVICES))
async def test_wait_ready_docker_warns_on_timeout(monkeypatch, cfg, report, service):
    monkeypatch.setattr(managed_service, "_http_ok", _async_false)
    await managed_service.phase_wait_ready(cfg, report, service=service, timeout=0)
    assert any("nada respondiendo" in msg for msg in report.warnings)


async def test_wait_ready_docker_is_noop_when_service_has_no_ready_url(cfg, report):
    service = dataclasses.replace(services.UNDERSTORY_SERVICE, ready_url_of=None)
    await managed_service.phase_wait_ready(cfg, report, service=service)
    assert report.successes == []
    assert report.warnings == []


@pytest.mark.parametrize("service", DOCKER_SERVICES, ids=_ids(DOCKER_SERVICES))
async def test_down_skips_when_dir_missing(cfg, report, tmp_path, service):
    service = _with_dir(service, tmp_path / "no-existe")
    await managed_service.phase_down(cfg, report, service=service)
    assert any("no encontrado" in msg for msg in report.warnings)


@pytest.mark.parametrize("service", DOCKER_SERVICES, ids=_ids(DOCKER_SERVICES))
async def test_down_succeeds(monkeypatch, cfg, report, tmp_path, service):
    service = _with_dir(service, tmp_path)
    fake, calls = _recording_docker_compose()
    monkeypatch.setattr(managed_service, "_docker_compose", fake)

    await managed_service.phase_down(cfg, report, service=service)

    assert calls[0] == ["down"]
    assert any("parado" in msg for msg in report.successes)


@pytest.mark.parametrize("service", DOCKER_SERVICES, ids=_ids(DOCKER_SERVICES))
async def test_down_raises_when_compose_down_fails(monkeypatch, cfg, report, tmp_path, service):
    service = _with_dir(service, tmp_path)
    fake, calls = _recording_docker_compose({"down": 1})
    monkeypatch.setattr(managed_service, "_docker_compose", fake)

    try:
        await managed_service.phase_down(cfg, report, service=service)
        raised = False
    except PhaseError:
        raised = True

    assert raised
    assert any("docker compose down falló" in msg for msg in report.errors)
