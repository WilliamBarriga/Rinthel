"""Aggregation de PhaseSpec en ServiceOutcome para POST /boot, /terminate y
/reload — ver docs/adr/0001.
`boot_units`/`down_units`/`reload_units` (lifecycle/specs.py) dan las fases
agrupadas por servicio; la conversión a `{"service", "ok", "message"}` en sí
vive en `phase_bridge.run_unit` y se prueba en tests/test_phase_bridge.py.
Acá se prueba que `boot`/`terminate`/`reload`/`install` respeten "corta en
el primer fallo" vs. "sigue con todas" sin tocar infra real (todo con
PhaseSpec/fases falsas)."""

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


async def test_terminate_runs_every_unit_even_if_one_raises_an_unexpected_exception(monkeypatch):
    """El caso que estaba roto antes de phase_bridge._run_phase_list_safe:
    una excepción que no es PhaseError (bug real, IO real) abortaba la
    list-comprehension de terminate() entera, y ninguna unidad posterior a
    la que explotó llegaba a correr — al revés de lo documentado en
    CONTEXT.md ("terminate sigue con las que quedan aunque una falle")."""

    async def _crashing_kill(cfg, report):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        daemon.specs,
        "down_units",
        lambda cfg: [
            ("llama-server", [PhaseSpec("kill", _crashing_kill)]),
            ("understory", [_ok_spec("down", "parado")]),
            ("pithagoras", [_ok_spec("down", "parado")]),
        ],
    )

    response = await daemon.terminate()
    body = json.loads(response.body)

    assert [r["service"] for r in body["results"]] == ["llama-server", "understory", "pithagoras"]
    assert [r["ok"] for r in body["results"]] == [False, True, True]
    assert "error inesperado" in body["results"][0]["message"]


# ── /reload ───────────────────────────────────────────────────────────
# Mismas 3 tandas de specs.reload_units + el chequeo de DOCKER que
# daemon.py inserta aparte entre shutdown y boot — corta en el primer
# fallo en cualquier punto de la secuencia completa, mismo criterio que
# /boot.


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


# ── phase_batch ───────────────────────────────────────────────────────────
# Ver docs/adr/0001: marca el límite entre tandas de /reload — sin
# esto el cliente no tenía forma de saber cuándo disparar Datamosh/Vignette
# (las 2 transiciones que reload.py corría client-side, imposibles de
# replicar contra un solo POST bloqueante orquestado del lado daemon).


async def _drain_broadcasts(monkeypatch) -> list[tuple[str, dict]]:
    seen: list[tuple[str, dict]] = []

    async def fake_broadcast(type_: str, data: dict) -> None:
        seen.append((type_, data))

    monkeypatch.setattr(daemon, "broadcast", fake_broadcast)
    return seen


async def test_reload_broadcasts_phase_batch_boot_then_rebuild(monkeypatch):
    monkeypatch.setattr(daemon.phases, "phase_check_docker", _ok_spec("docker", "activo").fn)
    _patch_reload_units(
        monkeypatch,
        shutdown=[("llama-server", [_ok_spec("kill", "parado")])],
        boot=[("llama-server", [_ok_spec("spawn", "lanzado"), _ok_spec("wait", "respondiendo")])],
        rebuild=[("understory", [_ok_spec("up", "levantado"), _ok_spec("wait", "respondiendo")])],
    )
    seen = await _drain_broadcasts(monkeypatch)

    await daemon.reload()

    batches = [data["batch"] for type_, data in seen if type_ == "phase_batch"]
    assert batches == ["boot", "rebuild"]


async def test_reload_never_broadcasts_a_shutdown_batch_marker(monkeypatch):
    """Nadie escucha "shutdown" del lado cliente (no hay transición antes de
    la primera tanda en el original) — no tiene sentido emitirla."""
    monkeypatch.setattr(daemon.phases, "phase_check_docker", _ok_spec("docker", "activo").fn)
    _patch_reload_units(
        monkeypatch,
        shutdown=[("llama-server", [_ok_spec("kill", "parado")])],
        boot=[],
        rebuild=[],
    )
    seen = await _drain_broadcasts(monkeypatch)

    await daemon.reload()

    batches = [data["batch"] for type_, data in seen if type_ == "phase_batch"]
    assert "shutdown" not in batches


async def test_reload_never_reaches_rebuild_batch_marker_if_boot_fails(monkeypatch):
    monkeypatch.setattr(daemon.phases, "phase_check_docker", _ok_spec("docker", "activo").fn)
    _patch_reload_units(
        monkeypatch,
        shutdown=[("llama-server", [_ok_spec("kill", "parado")])],
        boot=[("llama-server", [_failing_spec("spawn", "murió al instante")])],
        rebuild=[("understory", [_ok_spec("up", "nunca debería correr")])],
    )
    seen = await _drain_broadcasts(monkeypatch)

    await daemon.reload()

    batches = [data["batch"] for type_, data in seen if type_ == "phase_batch"]
    assert batches == ["boot"]


# ── /install ─────────────────────────────────────────────────────────────
# specs.install_units ya agrupa por InstallUnit (PREFLIGHT + una unidad por
# InstallUnit habilitada) — corta en el primer fallo, mismo criterio que
# /boot. Sin doble real: install corre subprocesos reales (clone/build CUDA/
# descarga del modelo) que no tiene sentido disparar en un test unitario, así
# que igual que boot/reload acá se prueba con PhaseSpec/fases falsas.


async def test_install_stops_at_first_failed_unit(monkeypatch):
    monkeypatch.setattr(
        daemon.specs,
        "install_units",
        lambda cfg: [
            ("preflight", [_failing_spec("preflight", "falta nvcc")]),
            ("llama.cpp + modelo", [_ok_spec("clone", "nunca debería correr")]),
        ],
    )

    response = await daemon.install()
    body = json.loads(response.body)

    assert [r["service"] for r in body["results"]] == ["preflight"]
    assert body["results"][0]["ok"] is False


async def test_install_runs_every_unit_when_all_succeed(monkeypatch):
    monkeypatch.setattr(
        daemon.specs,
        "install_units",
        lambda cfg: [
            ("preflight", [_ok_spec("preflight", "todo encontrado")]),
            ("llama.cpp + modelo", [_ok_spec("clone", "clonado"), _ok_spec("build", "compilado")]),
            ("pithagoras", [_ok_spec("setup", "configurado")]),
            ("understory", [_ok_spec("setup", "configurado")]),
        ],
    )

    response = await daemon.install()
    body = json.loads(response.body)

    assert [r["service"] for r in body["results"]] == [
        "preflight",
        "llama.cpp + modelo",
        "pithagoras",
        "understory",
    ]
    assert all(r["ok"] for r in body["results"])
