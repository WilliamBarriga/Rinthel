"""Aggregation de PhaseSpec en ServiceOutcome para POST /boot, /terminate y
/reload (sesión 04 + sesión 06 del port-map) — ver docs/adr/0001.
`boot_units`/`down_units`/`reload_units` (lifecycle/specs.py) dan las fases
agrupadas por servicio; acá se prueba que `daemon._run_unit`/`_Collected`
las conviertan en el `{"service", "ok", "message"}` que espera el cliente
Rust, y que `boot`/`terminate`/`reload` respeten "corta en el primer
fallo" vs. "sigue con todas" sin tocar infra real (todo con PhaseSpec/fases
falsas)."""

import json

from rinthel_tui import daemon
from rinthel_tui.lifecycle.specs import PhaseSpec
from rinthel_tui.lifecycle.types import PhaseError


def _ok_spec(label: str, msg: str) -> PhaseSpec:
    async def phase(cfg, report):
        report.success(msg)

    return PhaseSpec(label, phase)


def _failing_spec(label: str, msg: str) -> PhaseSpec:
    async def phase(cfg, report):
        report.error(msg)
        raise PhaseError(msg)

    return PhaseSpec(label, phase)


def _noisy_spec(label: str, msg: str) -> PhaseSpec:
    """Una fase que además reporta info() — no debería colarse en message."""

    async def phase(cfg, report):
        report.info("ruido de proceso, no es el resultado")
        report.success(msg)

    return PhaseSpec(label, phase)


async def test_run_unit_ok_true_and_concatenates_terminal_messages():
    outcome = await daemon._run_unit(
        "llama-server", [_ok_spec("spawn", "lanzado (PID 1)"), _ok_spec("wait", "respondiendo en :8080")]
    )
    assert outcome == {
        "service": "llama-server",
        "ok": True,
        "message": "lanzado (PID 1) — respondiendo en :8080",
    }


async def test_run_unit_drops_info_messages():
    outcome = await daemon._run_unit("llama-server", [_noisy_spec("spawn", "lanzado")])
    assert outcome["message"] == "lanzado"


async def test_run_unit_ok_false_when_a_phase_errors():
    outcome = await daemon._run_unit(
        "understory", [_ok_spec("up", "levantado"), _failing_spec("wait", "timeout esperando :3800")]
    )
    assert outcome["ok"] is False
    assert outcome["message"] == "levantado — timeout esperando :3800"


async def test_boot_stops_at_first_failed_service(monkeypatch):
    monkeypatch.setattr(daemon.phases, "phase_check_docker", _ok_spec("docker", "activo").fn)
    monkeypatch.setattr(
        daemon.specs,
        "boot_units",
        lambda cfg: [
            ("llama-server", [_failing_spec("spawn", "murió al instante")]),
            ("understory", [_ok_spec("up", "nunca debería correr")]),
        ],
    )

    response = await daemon.boot()
    body = json.loads(response.body)

    assert [r["service"] for r in body["results"]] == ["docker", "llama-server"]
    assert body["results"][-1]["ok"] is False


async def test_boot_never_touches_services_when_docker_check_fails(monkeypatch):
    monkeypatch.setattr(daemon.phases, "phase_check_docker", _failing_spec("docker", "DOCKER DAEMON INACTIVO").fn)
    called = False

    def _unexpected_boot_units(cfg):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(daemon.specs, "boot_units", _unexpected_boot_units)

    response = await daemon.boot()
    body = json.loads(response.body)

    assert body["results"] == [{"service": "docker", "ok": False, "message": "DOCKER DAEMON INACTIVO"}]
    assert called is False


async def test_terminate_runs_every_unit_even_if_one_fails(monkeypatch):
    monkeypatch.setattr(
        daemon.specs,
        "down_units",
        lambda cfg: [
            ("llama-server", [_failing_spec("kill", "AVISO: :8080 sigue ocupado")]),
            ("understory", [_ok_spec("down", "parado")]),
            ("pithagoras", [_ok_spec("down", "parado")]),
        ],
    )

    response = await daemon.terminate()
    body = json.loads(response.body)

    assert [r["service"] for r in body["results"]] == ["llama-server", "understory", "pithagoras"]
    assert [r["ok"] for r in body["results"]] == [False, True, True]


# ── /reload (sesión 06) ─────────────────────────────────────────────────
# Mismas 3 tandas de specs.reload_units + el chequeo de DOCKER que
# daemon.py inserta aparte entre shutdown y boot — corta en el primer
# fallo en cualquier punto de la secuencia completa, mismo criterio que
# /boot (grillado con Tarkark: replica _run_all de reload.py).


def _patch_reload_units(monkeypatch, shutdown, boot, rebuild):
    monkeypatch.setattr(daemon.specs, "reload_units", lambda cfg: (shutdown, boot, rebuild))


async def test_reload_runs_shutdown_docker_boot_rebuild_in_order(monkeypatch):
    monkeypatch.setattr(daemon.phases, "phase_check_docker", _ok_spec("docker", "activo").fn)
    _patch_reload_units(
        monkeypatch,
        shutdown=[("llama-server", [_ok_spec("kill", "parado")]), ("llama-server-port", [_ok_spec("wait", "libre")])],
        boot=[("llama-server", [_ok_spec("spawn", "lanzado"), _ok_spec("wait", "respondiendo")])],
        rebuild=[("understory", [_ok_spec("up", "levantado"), _ok_spec("wait", "respondiendo")])],
    )

    response = await daemon.reload()
    body = json.loads(response.body)

    assert [r["service"] for r in body["results"]] == [
        "llama-server",
        "llama-server-port",
        "docker",
        "llama-server",
        "understory",
    ]
    assert all(r["ok"] for r in body["results"])


async def test_reload_stops_at_first_failure_in_shutdown(monkeypatch):
    monkeypatch.setattr(daemon.phases, "phase_check_docker", _ok_spec("docker", "activo").fn)
    _patch_reload_units(
        monkeypatch,
        shutdown=[("llama-server", [_failing_spec("kill", "murió al instante")])],
        boot=[("understory", [_ok_spec("up", "nunca debería correr")])],
        rebuild=[],
    )

    response = await daemon.reload()
    body = json.loads(response.body)

    assert [r["service"] for r in body["results"]] == ["llama-server"]
    assert body["results"][0]["ok"] is False


async def test_reload_stops_when_docker_check_fails_before_boot(monkeypatch):
    monkeypatch.setattr(daemon.phases, "phase_check_docker", _failing_spec("docker", "DOCKER DAEMON INACTIVO").fn)
    _patch_reload_units(
        monkeypatch,
        shutdown=[("llama-server", [_ok_spec("kill", "parado")])],
        boot=[("llama-server", [_ok_spec("spawn", "nunca debería correr")])],
        rebuild=[("understory", [_ok_spec("up", "nunca debería correr")])],
    )

    response = await daemon.reload()
    body = json.loads(response.body)

    assert [r["service"] for r in body["results"]] == ["llama-server", "docker"]
    assert body["results"][-1]["ok"] is False
