"""Daemon FastAPI de Rinthel — infraestructura persistente e independiente
del cliente: el daemon Python es lo que sobrevive entre sesiones de la TUI,
el binario Rust es el cliente reemplazable.

Corré con:  .venv/bin/python -m rinthel_tui.daemon   (o el entry point
``rinthel-daemon``, ver pyproject.toml)

``/capture`` está SIMULADO a propósito — no corre lifecycle/capture_profile.py
real (no dispara llama-moe-trace contra la GPU). Todo lo demás (boot,
terminate, reload, install, GPU, CPU/RAM, docker ps, tail de log) es real.

Endpoints:

- ``POST /boot``/``/terminate``/``/reload``/``/install`` corren las fases de
  ``lifecycle/runner.py`` + ``lifecycle/specs.py``, bloqueantes, y devuelven
  ``{"results": [ServiceOutcome]}`` como única fuente de verdad. Boot/reload/
  install cortan en el primer fallo; terminate sigue con lo que queda aunque
  una unidad falle.
- ``GET``/``POST /config``: el daemon es dueño de todo ``RinthelConfig``; el
  cliente Rust no duplica ``config._ENTRIES`` ni parsea ``.env``. El shape
  genérico de la respuesta y el ciclo validar-antes-de-escribir viven en
  ``config_routes.py`` — acá solo el wiring HTTP y el dueño único del ``cfg``
  en memoria.
- ``/ws/monitor`` multiplexa, con un sobre ``{"type", "data"}`` por mensaje:
  telemetría periódica (``docker_status``, ``gpu_sample``, ``cpu_ram_sample``,
  ``log_line``, ``llama_status``) y progreso de una corrida en curso
  (``phase_status``, ``phase_log``, ``phase_batch``). Todo esto es
  best-effort y fire-and-forget (``asyncio.create_task``, no awaited): perder
  un mensaje de progreso no afecta el ``ServiceOutcome`` final que viaja por
  la respuesta del POST. Sin cliente conectado, ``broadcast`` es un no-op.
  El puente entre ``PhaseReport`` y ``phase_status``/``phase_log`` vive en
  ``phase_bridge.py`` (``_Collected``/``_BroadcastingCollected``/``run_unit``).
  ``phase_batch`` (``{"batch": "boot"|"rebuild"}``) marca el límite entre
  tandas de ``/reload`` (shutdown → boot → rebuild), que corre las 3 de un
  tirón sin otro marcador — el cliente lo usa para disparar sus transiciones
  visuales entre tandas. ``"shutdown"`` no se emite: no hay transición antes
  de la primera tanda.
- ``llama_status`` (``{"ready": bool}``) es un estado parado, no un evento de
  corrida puntual: un GET sin backoff contra el mismo ``ready_url_of`` que ya
  usa ``phase_wait_ready`` en boot/reload. En llama-server ese endpoint queda
  detrás de un único gate que solo se levanta con el modelo cargado, así que
  "ready" ya implica servidor arriba + modelo cargado.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from rinthel_tui import config_routes, phase_bridge
from rinthel_tui.config import default_config
from rinthel_tui.lifecycle import phases, specs
from rinthel_tui.lifecycle.managed_service import check_ready
from rinthel_tui.lifecycle.services import DOCKER_SERVICES, LLAMA_SERVICE, LOCAL_SERVICES
from rinthel_tui.lifecycle.specs import PhaseSpec
from rinthel_tui.monitoring.resources import read_cpu_ram, read_gpu
from rinthel_tui.monitoring.services import docker_compose_ps
from rinthel_tui.theme import palette

cfg = default_config()
app = FastAPI()

# rinthel_tui/daemon.py -> repo root (mismo criterio que config.py para
# ubicar el .env de la raíz).
_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _REPO_ROOT / ".env"
_ENV_EXAMPLE_PATH = _REPO_ROOT / ".env.example"

MANAGED_SERVICES = [*LOCAL_SERVICES, *DOCKER_SERVICES]  # mismo orden que boot/terminate reales

# Clientes /ws/monitor conectados ahora mismo — Rinthel es monousuario así
# que en la práctica hay 0 o 1, pero el set soporta más sin cambios.
_ws_clients: set[WebSocket] = set()


async def broadcast(type_: str, data: dict) -> None:
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_text(json.dumps({"type": type_, "data": data}))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)


@app.get("/theme")
def get_theme() -> JSONResponse:
    return JSONResponse(
        {
            "canonical": {
                "fg": palette.FG,
                "accent": palette.ACCENT,
                "electric": palette.ELECTRIC,
                "warn": palette.WARN,
                "success": palette.SUCCESS,
                "hot": palette.HOT,
                "caution": palette.CAUTION,
                "glow": palette.GLOW,
                "dim": palette.DIM,
                "bg": palette.BG,
            },
            "extended": {
                "cool": palette.COOL,
                "cool_dim": palette.COOL_DIM,
                "hot_dim": palette.HOT_DIM,
                "electric_dim": palette.ELECTRIC_DIM,
                "steel": palette.STEEL,
                "steel_dim": palette.STEEL_DIM,
                "accent_dim": palette.ACCENT_DIM,
            },
            "frame_chars": list(palette.FRAME_CHARS),
        }
    )


@app.get("/config")
def get_config() -> JSONResponse:
    return JSONResponse(config_routes.config_payload(cfg))


@app.post("/config")
async def post_config(payload: dict) -> JSONResponse:
    # Reemplaza `cfg` (el módulo-global, no solo el archivo) por el
    # RinthelConfig ya validado tras un write propio, para que un GET
    # inmediato después no siga mostrando el valor viejo.
    global cfg
    updated, result = config_routes.apply_config_overrides(
        cfg, payload.get("overrides", {}), _ENV_PATH, _ENV_EXAMPLE_PATH
    )
    if updated is not None:
        cfg = updated
    return JSONResponse(result)


def _tail_lines(path, n: int) -> list[str]:
    if not path.exists():
        return []
    with path.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        block = min(size, 1 << 16)
        lines: list[str] = []
        while len(lines) <= n and block <= size:
            f.seek(-block, 2)
            lines = f.read().decode(errors="replace").splitlines()
            if block == size:
                break
            block = min(block * 2, size)
        return lines[-n:]


async def _log_line_source():
    """Yields new lines from cfg.llama.log (real tail -f), o un generador
    sintético si el archivo no existe — lectura pura, nunca escribe."""
    path = cfg.llama.log
    backlog = _tail_lines(path, 50)
    for line in backlog:
        yield line
    if not path.exists():
        i = 0
        while True:
            await asyncio.sleep(1.0)
            i += 1
            yield f"[daemon] sin {path} real — línea sintética #{i}"
        return
    pos = path.stat().st_size
    while True:
        await asyncio.sleep(0.5)
        size = path.stat().st_size
        if size < pos:  # log rotado
            pos = 0
        if size > pos:
            with path.open("rb") as f:
                f.seek(pos)
                chunk = f.read()
                pos = f.tell()
            for line in chunk.decode(errors="replace").splitlines():
                if line:
                    yield line


@app.websocket("/ws/monitor")
async def ws_monitor(ws: WebSocket) -> None:
    await ws.accept()
    _ws_clients.add(ws)

    async def send(type_: str, data: dict) -> None:
        await ws.send_text(json.dumps({"type": type_, "data": data}))

    async def docker_status_task():
        while True:
            containers = []
            for svc in DOCKER_SERVICES:
                containers += [asdict(c) for c in await docker_compose_ps(svc.dir_of(cfg))]
            await send("docker_status", {"containers": containers})
            await asyncio.sleep(3.0)

    async def gpu_task():
        while True:
            await send("gpu_sample", asdict(await read_gpu()))
            await asyncio.sleep(1.5)

    async def cpu_ram_task():
        while True:
            await send("cpu_ram_sample", asdict(await read_cpu_ram()))
            await asyncio.sleep(1.5)

    async def log_task():
        async for line in _log_line_source():
            await send("log_line", {"line": line})

    async def llama_status_task():
        while True:
            await send("llama_status", {"ready": await check_ready(cfg, LLAMA_SERVICE)})
            await asyncio.sleep(2.0)

    tasks = [
        asyncio.create_task(docker_status_task()),
        asyncio.create_task(gpu_task()),
        asyncio.create_task(cpu_ram_task()),
        asyncio.create_task(log_task()),
        asyncio.create_task(llama_status_task()),
    ]
    try:
        while True:
            await ws.receive_text()  # el cliente no manda nada; solo detecta disconnect
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)
        for t in tasks:
            t.cancel()


@app.post("/boot")
async def boot() -> JSONResponse:
    results = [
        await phase_bridge.run_unit(cfg, "docker", [PhaseSpec("◈ DOCKER", phases.phase_check_docker)], broadcast)
    ]
    if results[0]["ok"]:
        for service, unit_specs in specs.boot_units(cfg):
            outcome = await phase_bridge.run_unit(cfg, service, unit_specs, broadcast)
            results.append(outcome)
            if not outcome["ok"]:
                break  # boot corta en el primer fallo
    return JSONResponse({"results": results})


@app.post("/terminate")
async def terminate() -> JSONResponse:
    results = [
        await phase_bridge.run_unit(cfg, service, unit_specs, broadcast)
        for service, unit_specs in specs.down_units(cfg)
    ]
    return JSONResponse({"results": results})


@app.post("/reload")
async def reload() -> JSONResponse:
    # shutdown → DOCKER → boot(solo local) → rebuild(solo docker, no_cache),
    # mismo trío phase_status/phase_log que boot/terminate, corta en el
    # primer fallo. `phase_batch` marca el límite antes de "boot" y antes de
    # "rebuild" para que el cliente sepa cuándo disparar sus transiciones.
    shutdown, boot, rebuild = specs.reload_units(cfg)
    docker_check = ("docker", [PhaseSpec("◈ DOCKER", phases.phase_check_docker)])
    groups: list[tuple[str | None, list[tuple[str, list[PhaseSpec]]]]] = [
        (None, shutdown),
        ("boot", [docker_check, *boot]),
        ("rebuild", rebuild),
    ]
    results = []
    for batch, units in groups:
        if batch is not None:
            await broadcast("phase_batch", {"batch": batch})
        for service, unit_specs in units:
            outcome = await phase_bridge.run_unit(cfg, service, unit_specs, broadcast)
            results.append(outcome)
            if not outcome["ok"]:
                return JSONResponse({"results": results})
    return JSONResponse({"results": results})


async def _simulate_service(name: str, seconds: float, ok: bool, message: str) -> dict:
    await asyncio.sleep(seconds)
    return {"service": name, "ok": ok, "message": message}


@app.post("/install")
async def install() -> JSONResponse:
    # Mismo mecanismo bloqueante + phase_status/phase_log que boot/terminate/
    # reload. Corta en el primer fallo: si PREFLIGHT falla (falta CUDA/docker)
    # no tiene sentido seguir con clone/build/descarga.
    results = []
    for service, unit_specs in specs.install_units(cfg):
        outcome = await phase_bridge.run_unit(cfg, service, unit_specs, broadcast)
        results.append(outcome)
        if not outcome["ok"]:
            break
    return JSONResponse({"results": results})


@app.post("/capture")
async def capture() -> JSONResponse:
    # SIMULADO a propósito, igual que boot/terminate lo fueron antes de
    # tener lifecycle real detrás. No corre lifecycle/capture_profile.py real
    # (no dispara llama-moe-trace contra la GPU).
    # `results[].service` reusa el campo de `ServiceOutcome` para nombrar
    # cada sub-paso de `capture_profile` ("código"/"chat"), no un servicio.
    plan = [
        ("código", 1.5, True, "listo (simulado)"),
        ("chat", 1.5, True, "listo (simulado)"),
    ]
    results = []
    for name, secs, ok, msg in plan:
        outcome = await _simulate_service(name, secs, ok, msg)
        results.append(outcome)
        if not outcome["ok"]:
            break  # mismo criterio que boot: corta en el primer fallo
    return JSONResponse({"results": results})


def main() -> None:
    import uvicorn

    # Puerto propio del daemon (distinto de los 3 servicios reales) —
    # overrideable por `.env`; `rinthel-boot.sh` lo lee de ahí y se lo pasa
    # al binario Rust como `--port`, default 8765 si nadie lo setea.
    port = int(os.getenv("RINTHEL_DAEMON_PORT", "8765"))
    print(f"[daemon] {time.strftime('%H:%M:%S')} arrancando en http://127.0.0.1:{port}")
    print(f"[daemon] tail real de: {cfg.llama.log}")
    # workers=1 a propósito, no el default implícito de uvicorn: `cfg` y
    # `_ws_clients` son globals mutables sin lock (post_config reasigna
    # `cfg` con `global`, _ws_clients asume "0 o 1 cliente" en todo
    # ws_monitor). Con más de un worker cada proceso vería su propia copia
    # de `cfg` tras un POST /config — Rinthel es monousuario, no hace falta
    # más de uno.
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", workers=1)


if __name__ == "__main__":
    main()
