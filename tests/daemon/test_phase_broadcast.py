"""Canal de progreso en vivo de boot/terminate por /ws/monitor (sesión 05
del port-map, amendment de docs/adr/0001) — prueba que `_run_unit` emita
`phase_status`/`phase_log` por cada fase/llamada a report, sin tocar el
`ServiceOutcome` final (eso ya lo cubre test_aggregation.py) ni requerir un
WebSocket real conectado."""

import asyncio

from rinthel_tui import daemon
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


async def _drain_broadcasts(monkeypatch) -> list[tuple[str, dict]]:
    """Reemplaza daemon.broadcast por uno que junta los envíos en una lista
    en vez de mandarlos a _ws_clients — evita levantar un WebSocket real
    para probar el wiring de _run_unit."""
    seen: list[tuple[str, dict]] = []

    async def fake_broadcast(type_: str, data: dict) -> None:
        seen.append((type_, data))

    monkeypatch.setattr(daemon, "broadcast", fake_broadcast)
    return seen


async def _run_and_flush(coro):
    """asyncio.create_task en _BroadcastingCollected es fire-and-forget —
    hace falta cederle el loop una vez para que los tasks encolados corran
    antes de leer `seen`."""
    result = await coro
    await asyncio.sleep(0)
    return result


async def test_run_unit_broadcasts_phase_status_running_then_done(monkeypatch):
    seen = await _drain_broadcasts(monkeypatch)

    await _run_and_flush(daemon._run_unit("llama-server", [_ok_spec("spawn", "lanzado")]))

    statuses = [data for type_, data in seen if type_ == "phase_status"]
    assert statuses == [
        {"label": "spawn", "status": "running"},
        {"label": "spawn", "status": "done"},
    ]


async def test_run_unit_broadcasts_phase_status_error_on_failure(monkeypatch):
    seen = await _drain_broadcasts(monkeypatch)

    await _run_and_flush(daemon._run_unit("llama-server", [_failing_spec("wait", "timeout")]))

    statuses = [data for type_, data in seen if type_ == "phase_status"]
    assert statuses == [
        {"label": "wait", "status": "running"},
        {"label": "wait", "status": "error"},
    ]


async def test_run_unit_broadcasts_phase_log_including_info(monkeypatch):
    """A diferencia del `message` final (ver test_run_unit_drops_info_messages
    en test_aggregation.py), el canal en vivo sí transmite info() — es lo que
    ScreenPhaseReport mostraba en Textual."""
    seen = await _drain_broadcasts(monkeypatch)

    await _run_and_flush(daemon._run_unit("llama-server", [_noisy_spec("spawn", "lanzado")]))

    logs = [data for type_, data in seen if type_ == "phase_log"]
    assert logs == [
        {"kind": "info", "message": "ruido de proceso"},
        {"kind": "success", "message": "lanzado"},
    ]


async def test_run_unit_broadcasts_two_specs_in_order(monkeypatch):
    seen = await _drain_broadcasts(monkeypatch)

    await _run_and_flush(
        daemon._run_unit(
            "llama-server", [_ok_spec("spawn", "lanzado"), _ok_spec("wait", "respondiendo")]
        )
    )

    labels = [data["label"] for type_, data in seen if type_ == "phase_status"]
    assert labels == ["spawn", "spawn", "wait", "wait"]


async def test_broadcast_is_noop_with_no_connected_clients():
    daemon._ws_clients.clear()
    await daemon.broadcast("phase_status", {"label": "x", "status": "running"})  # no debe levantar
