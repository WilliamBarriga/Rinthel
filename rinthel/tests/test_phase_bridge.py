"""``phase_bridge.run_unit`` — adapta ``PhaseReport`` a ``ServiceOutcome``
(``{"service", "ok", "message"}``) y a la telemetría ``phase_status``/
``phase_log`` de ``/ws/monitor``. ``broadcast`` se inyecta como argumento
(ver phase_bridge.py) — no hace falta monkeypatchear nada ni levantar un
WebSocket real, alcanza con pasarle una función de prueba."""

import asyncio

from rinthel_tui import phase_bridge
from rinthel_tui.lifecycle.specs import PhaseSpec
from rinthel_tui.lifecycle.types import PhaseError


def _ok_spec(label: str, msg: str) -> PhaseSpec:
    async def phase(cfg, report):
        report.success(msg)

    return PhaseSpec(label, phase)


def _noisy_spec(label: str, msg: str) -> PhaseSpec:
    async def phase(cfg, report):
        report.info("ruido de proceso")
        report.success(msg)

    return PhaseSpec(label, phase)


def _failing_spec(label: str, msg: str) -> PhaseSpec:
    async def phase(cfg, report):
        report.error(msg)
        raise PhaseError(msg)

    return PhaseSpec(label, phase)


def _crashing_spec(label: str) -> PhaseSpec:
    """Una fase con un bug real (o una excepción de IO genuina) — algo que
    no es PhaseError, y que ninguna fase de managed_service.py/install.py
    levanta hoy a propósito, pero que un bug real podría."""

    async def phase(cfg, report):
        raise RuntimeError("boom")

    return PhaseSpec(label, phase)


def _collecting_broadcast():
    seen: list[tuple[str, dict]] = []

    async def broadcast(type_: str, data: dict) -> None:
        seen.append((type_, data))

    return broadcast, seen


async def _run_and_flush(coro):
    """asyncio.create_task en _BroadcastingCollected es fire-and-forget —
    hace falta cederle el loop una vez para que los tasks encolados corran
    antes de leer `seen`."""
    result = await coro
    await asyncio.sleep(0)
    return result


# ── ServiceOutcome (ok/message) ──────────────────────────────────────────


async def test_run_unit_ok_true_and_concatenates_terminal_messages(cfg):
    broadcast, _seen = _collecting_broadcast()
    outcome = await phase_bridge.run_unit(
        cfg,
        "llama-server",
        [_ok_spec("spawn", "lanzado (PID 1)"), _ok_spec("wait", "respondiendo en :8080")],
        broadcast,
    )
    assert outcome == {
        "service": "llama-server",
        "ok": True,
        "message": "lanzado (PID 1) — respondiendo en :8080",
    }


async def test_run_unit_drops_info_messages(cfg):
    broadcast, _seen = _collecting_broadcast()
    outcome = await phase_bridge.run_unit(cfg, "llama-server", [_noisy_spec("spawn", "lanzado")], broadcast)
    assert outcome["message"] == "lanzado"


async def test_run_unit_ok_false_when_a_phase_errors(cfg):
    broadcast, _seen = _collecting_broadcast()
    outcome = await phase_bridge.run_unit(
        cfg,
        "understory",
        [_ok_spec("up", "levantado"), _failing_spec("wait", "timeout esperando :3800")],
        broadcast,
    )
    assert outcome["ok"] is False
    assert outcome["message"] == "levantado — timeout esperando :3800"


# ── excepciones no previstas (no PhaseError) — punto #3 del reporte de
# robustez: antes de esto, algo que no fuera PhaseError se propagaba fuera
# de run_phase_list sin convertirse en un ServiceOutcome. ──────────────────


async def test_run_unit_ok_false_on_unexpected_exception_instead_of_propagating(cfg):
    broadcast, _seen = _collecting_broadcast()
    outcome = await phase_bridge.run_unit(cfg, "llama-server", [_crashing_spec("spawn")], broadcast)
    assert outcome["ok"] is False
    assert "error inesperado" in outcome["message"]


async def test_run_unit_unexpected_exception_does_not_stop_the_next_unit(cfg):
    """El caso que estaba roto de verdad: /terminate corre varias unidades
    en secuencia (ver daemon.py::terminate, specs.down_units) y depende de
    que una excepción no prevista en una no aborte las siguientes — "sigue
    con las que quedan aunque una falle" (CONTEXT.md, entrada "Boot /
    Terminate"). Antes del fix, esto rompía la list-comprehension entera y
    ninguna unidad posterior a la que explotó llegaba a correr."""
    broadcast, _seen = _collecting_broadcast()
    first = await phase_bridge.run_unit(cfg, "llama-server", [_crashing_spec("kill")], broadcast)
    second = await phase_bridge.run_unit(cfg, "understory", [_ok_spec("down", "parado")], broadcast)
    assert first["ok"] is False
    assert second == {"service": "understory", "ok": True, "message": "parado"}


# ── telemetría phase_status/phase_log ─────────────────────────────────────


async def test_run_unit_broadcasts_phase_status_running_then_done(cfg):
    broadcast, seen = _collecting_broadcast()
    await _run_and_flush(phase_bridge.run_unit(cfg, "llama-server", [_ok_spec("spawn", "lanzado")], broadcast))

    statuses = [data for type_, data in seen if type_ == "phase_status"]
    assert statuses == [
        {"label": "spawn", "status": "running"},
        {"label": "spawn", "status": "done"},
    ]


async def test_run_unit_broadcasts_phase_status_error_on_failure(cfg):
    broadcast, seen = _collecting_broadcast()
    await _run_and_flush(phase_bridge.run_unit(cfg, "llama-server", [_failing_spec("wait", "timeout")], broadcast))

    statuses = [data for type_, data in seen if type_ == "phase_status"]
    assert statuses == [
        {"label": "wait", "status": "running"},
        {"label": "wait", "status": "error"},
    ]


async def test_run_unit_broadcasts_phase_log_including_info(cfg):
    """A diferencia del `message` final (ver test_run_unit_drops_info_messages),
    el canal en vivo sí transmite info() — es lo que el cliente muestra en
    vivo."""
    broadcast, seen = _collecting_broadcast()
    await _run_and_flush(phase_bridge.run_unit(cfg, "llama-server", [_noisy_spec("spawn", "lanzado")], broadcast))

    logs = [data for type_, data in seen if type_ == "phase_log"]
    assert logs == [
        {"kind": "info", "message": "ruido de proceso"},
        {"kind": "success", "message": "lanzado"},
    ]


async def test_run_unit_broadcasts_two_specs_in_order(cfg):
    broadcast, seen = _collecting_broadcast()
    await _run_and_flush(
        phase_bridge.run_unit(
            cfg, "llama-server", [_ok_spec("spawn", "lanzado"), _ok_spec("wait", "respondiendo")], broadcast
        )
    )

    labels = [data["label"] for type_, data in seen if type_ == "phase_status"]
    assert labels == ["spawn", "spawn", "wait", "wait"]
