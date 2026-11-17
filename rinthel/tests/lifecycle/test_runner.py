"""Ejemplo de la categoría 'lifecycle/runner' — orquestación de PhaseSpec.

Estilo: fases falsas definidas ad-hoc (no las reales de phases.py/install.py)
para aislar el comportamiento de run_phase_list en sí mismo.
"""

from rinthel_tui.lifecycle.phases import PhaseError
from rinthel_tui.lifecycle.runner import PhaseFailed, run_phase_list
from rinthel_tui.lifecycle.specs import PhaseSpec


async def test_run_phase_list_wraps_phase_error_in_phase_failed(cfg, report):
    async def ok_phase(cfg, report):
        report.success("fase 1 ok")

    async def failing_phase(cfg, report):
        raise PhaseError("boom")

    specs = [
        PhaseSpec("fase 1", ok_phase),
        PhaseSpec("fase 2 (falla)", failing_phase),
    ]

    events: list[tuple[str, str]] = []

    def on_phase(spec: PhaseSpec, status: str) -> None:
        events.append((spec.label, status))

    try:
        await run_phase_list(cfg, specs, report, on_phase=on_phase)
        failed = None
    except PhaseFailed as exc:
        failed = exc

    assert failed is not None
    assert failed.label == "fase 2 (falla)"
    assert isinstance(failed.cause, PhaseError)
    assert events == [
        ("fase 1", "running"),
        ("fase 1", "done"),
        ("fase 2 (falla)", "running"),
        ("fase 2 (falla)", "error"),
    ]


async def test_run_phase_list_stops_before_phases_after_the_failure(cfg, report):
    ran: list[str] = []

    async def failing_phase(cfg, report):
        ran.append("fase 1")
        raise PhaseError("boom")

    async def never_runs(cfg, report):
        ran.append("fase 2")

    specs = [
        PhaseSpec("fase 1 (falla)", failing_phase),
        PhaseSpec("fase 2", never_runs),
    ]

    try:
        await run_phase_list(cfg, specs, report)
    except PhaseFailed:
        pass

    assert ran == ["fase 1"]


async def test_run_phase_list_runs_all_phases_when_none_fail(cfg, report):
    ran: list[str] = []

    def make_phase(name: str):
        async def phase(cfg, report):
            ran.append(name)

        return phase

    specs = [
        PhaseSpec("fase 1", make_phase("fase 1")),
        PhaseSpec("fase 2", make_phase("fase 2")),
    ]

    await run_phase_list(cfg, specs, report)

    assert ran == ["fase 1", "fase 2"]
