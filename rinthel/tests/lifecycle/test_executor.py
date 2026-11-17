"""``executor.execute`` — corre cualquier Lifecycle plan (ver GLOSSARY.md)
contra un ``broadcast`` inyectado y devuelve un ``UnitOutcome`` por
unidad. Plans y fases falsos, ``broadcast`` que registra — sin
monkeypatch ni infra real."""

import asyncio

import pytest

from rinthel_tui.lifecycle import executor, install, install_tasks
from rinthel_tui.lifecycle.domain.errors import PhaseError
from rinthel_tui.lifecycle.domain.types import UnitOutcome
from rinthel_tui.lifecycle.specs import Batch, PhaseSpec, Plan, Unit
from tests.lifecycle.fakes import fake_host


@pytest.fixture
def host():
    return fake_host()[0]


@pytest.fixture
def broadcasts() -> list[tuple[str, dict]]:
    return []


@pytest.fixture
def broadcast(broadcasts):
    async def _broadcast(type_: str, data: dict) -> None:
        broadcasts.append((type_, data))

    return _broadcast


def _ok(label: str, msg: str) -> PhaseSpec:
    async def phase(cfg, report):
        report.success(msg)

    return PhaseSpec(label, phase)


def _failing(label: str, msg: str) -> PhaseSpec:
    async def phase(cfg, report):
        report.error(msg)
        raise PhaseError(msg)

    return PhaseSpec(label, phase)


def _plan(on_failure: str, *units: Unit) -> Plan:
    return Plan(on_failure=on_failure, batches=(Batch(marker=None, units=units),))


# ── UnitOutcome ──────────────────────────────────────────────────────


async def test_one_outcome_per_unit_concatenating_terminal_messages(cfg, host, broadcast):
    plan = _plan(
        "stop",
        Unit("llama-server", (_ok("spawn", "lanzado (PID 1)"), _ok("wait", "respondiendo en :8080"))),
        Unit("understory", (_ok("up", "levantado"),)),
    )

    results = await executor.execute(plan, broadcast, host)

    assert results == [
        UnitOutcome(service="llama-server", ok=True, message="lanzado (PID 1) — respondiendo en :8080"),
        UnitOutcome(service="understory", ok=True, message="levantado"),
    ]


# ── failure policy ──────────────────────────────────────────────────────


async def test_stop_plan_ends_at_first_failed_unit(cfg, host, broadcast):
    plan = _plan(
        "stop",
        Unit("llama-server", (_ok("spawn", "lanzado"), _failing("wait", "timeout esperando :8080"))),
        Unit("understory", (_ok("up", "nunca debería correr"),)),
    )

    results = await executor.execute(plan, broadcast, host)

    assert results == [
        UnitOutcome(service="llama-server", ok=False, message="lanzado — timeout esperando :8080"),
    ]


async def test_llamacpp_configure_failure_reaches_service_outcome(cfg, host, broadcast, tmp_path):
    task = install_tasks.LlamaCppInstall(tmp_path / "llama.cpp", "https://example.test/llama.cpp", "master")
    host.host_info.install_cuda("/usr/local/cuda-12.8/bin/nvcc")
    host.runner.script_program("cmake", rc=2, output="configure failed")
    plan = _plan("stop", Unit("llama.cpp + modelo", (
        PhaseSpec("build CUDA", install.phase_install_build_llamacpp, {"task": task}),
    )))

    outcomes = await executor.execute(plan, broadcast, host)

    (outcome,) = outcomes
    assert outcome.service == "llama.cpp + modelo" and outcome.ok is False
    assert "cmake configure falló (rc 2)" in outcome.message
    assert len(host.runner.ran("cmake")) == 1


async def test_phases_after_a_failed_phase_never_run_even_in_a_continue_plan(cfg, host, broadcast):
    """Dentro de una unidad las fases dependen de la anterior (no tiene
    sentido esperar a llama-server si no se lo pudo lanzar): el plan
    ``continue`` sigue con la unidad siguiente, no con la fase siguiente."""
    plan = _plan(
        "continue",
        Unit("llama-server", (_failing("spawn", "murió al instante"), _ok("wait", "nunca debería correr"))),
        Unit("understory", (_ok("down", "parado"),)),
    )

    results = await executor.execute(plan, broadcast, host)

    assert results == [
        UnitOutcome(service="llama-server", ok=False, message="murió al instante"),
        UnitOutcome(service="understory", ok=True, message="parado"),
    ]


async def test_continue_plan_runs_every_unit_even_if_one_raises_unexpectedly(cfg, host, broadcast):
    """Una excepción que no es PhaseError (bug, IO real) cuenta como fallo
    de esa unidad, no aborta el plan — terminate "sigue con las que quedan
    aunque una falle" (GLOSSARY.md, Boot / Terminate)."""

    async def crash(cfg, report):
        raise RuntimeError("boom")

    plan = _plan(
        "continue",
        Unit("llama-server", (PhaseSpec("kill", crash),)),
        Unit("understory", (_failing("down", "no respondió"),)),
        Unit("deck", (_ok("down", "parado"),)),
    )

    results = await executor.execute(plan, broadcast, host)

    assert results == [
        UnitOutcome(service="llama-server", ok=False, message="error inesperado: boom"),
        UnitOutcome(service="understory", ok=False, message="no respondió"),
        UnitOutcome(service="deck", ok=True, message="parado"),
    ]


# ── telemetría phase_status / phase_log ─────────────────────────────────


async def test_broadcasts_status_and_log_in_phase_order(cfg, host, broadcast, broadcasts):
    """``phase_log`` se awaitea: llega entre el running y el done/error de su
    fase, sin ceder el loop. ``info()`` viaja en vivo aunque quede fuera del
    ``message`` final."""

    async def noisy(cfg, report):
        report.info("ruido de proceso")
        report.success("lanzado")

    plan = _plan("stop", Unit("llama-server", (PhaseSpec("spawn", noisy), _failing("wait", "timeout"))))

    results = await executor.execute(plan, broadcast, host)

    assert broadcasts == [
        ("phase_status", {"label": "spawn", "status": "running"}),
        ("phase_log", {"kind": "info", "message": "ruido de proceso"}),
        ("phase_log", {"kind": "success", "message": "lanzado"}),
        ("phase_status", {"label": "spawn", "status": "done"}),
        ("phase_status", {"label": "wait", "status": "running"}),
        ("phase_log", {"kind": "error", "message": "timeout"}),
        ("phase_status", {"label": "wait", "status": "error"}),
    ]
    assert results[0].message == "lanzado — timeout"


# ── phase_batch ─────────────────────────────────────────────────────────


async def test_batch_markers_open_each_batch_and_none_is_silent(cfg, host, broadcast, broadcasts):
    plan = Plan(
        on_failure="stop",
        batches=(
            Batch(marker=None, units=(Unit("llama-server", (_ok("kill", "parado"),)),)),
            Batch(marker="boot", units=(Unit("llama-server", (_ok("spawn", "lanzado"),)),)),
            Batch(marker="rebuild", units=(Unit("understory", (_ok("up", "levantado"),)),)),
        ),
    )

    await executor.execute(plan, broadcast, host)

    assert [(t, d) for t, d in broadcasts if t == "phase_batch"] == [
        ("phase_batch", {"batch": "boot"}),
        ("phase_batch", {"batch": "rebuild"}),
    ]
    # el marcador abre la tanda: va antes del primer phase_status de su unidad
    boot_marker = broadcasts.index(("phase_batch", {"batch": "boot"}))
    assert broadcasts[boot_marker + 1] == ("phase_status", {"label": "spawn", "status": "running"})


async def test_stop_before_a_batch_never_broadcasts_its_marker(cfg, host, broadcast, broadcasts):
    plan = Plan(
        on_failure="stop",
        batches=(
            Batch(marker="boot", units=(Unit("llama-server", (_failing("spawn", "murió al instante"),)),)),
            Batch(marker="rebuild", units=(Unit("understory", (_ok("up", "nunca debería correr"),)),)),
        ),
    )

    results = await executor.execute(plan, broadcast, host)

    assert [d["batch"] for t, d in broadcasts if t == "phase_batch"] == ["boot"]
    assert [r.service for r in results] == ["llama-server"]


# ── cancelación ─────────────────────────────────────────────────────────


async def test_cancelled_phase_propagates_and_leaves_no_pending_task(cfg, host, broadcast):
    """``CancelledError`` no es un fallo de la fase: sube tal cual, sin
    dejar colgado el task que transmite los ``phase_log``."""

    async def cancelled(cfg, report):
        report.info("arrancando")
        raise asyncio.CancelledError

    plan = _plan("continue", Unit("llama-server", (PhaseSpec("spawn", cancelled),)))

    with pytest.raises(asyncio.CancelledError):
        await executor.execute(plan, broadcast, host)
    await asyncio.sleep(0)

    assert asyncio.all_tasks() == {asyncio.current_task()}
