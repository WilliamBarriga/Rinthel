"""SPIKE — daemon FastAPI, no producción.

Prototipo del ticket "Construir el spike MVP" (.scratch/ratatui-migration/
issues/05-mvp-spike.md), tirado en una rama throwaway (`spike/ratatui-mvp-05`).
Valida el protocolo diseñado en el ticket 03 (ver docs/adr/0001-daemon-protocol-shape.md)
contra un cliente Ratatui real. Si el diseño se valida, esto se refunda como
``rinthel_tui/daemon.py`` de verdad (ticket 04) — hasta entonces es código
descartable, sin tests, sin manejo de errores más allá de lo que hace falta
para que corra.

Corré con:  .venv/bin/python -m rinthel_tui.daemon_spike

A propósito NO ejecuta boot/terminate reales (no arranca/mata llama-server,
Understory ni Pithagoras de verdad) — el spike valida forma de protocolo y
UX de streaming, no re-implementa lifecycle/runner.py. Todo lo demás (GPU,
CPU/RAM, docker ps, tail de log) es de solo lectura contra el sistema real.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from rinthel_tui.config import default_config
from rinthel_tui.lifecycle.services import DOCKER_SERVICES, LOCAL_SERVICES
from rinthel_tui.monitoring.resources import read_cpu_ram, read_gpu
from rinthel_tui.monitoring.services import docker_compose_ps
from rinthel_tui.theme import palette

cfg = default_config()
app = FastAPI()

MANAGED_SERVICES = [*LOCAL_SERVICES, *DOCKER_SERVICES]  # mismo orden que boot/terminate reales


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
            yield f"[spike] sin {path} real — línea sintética #{i}"
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

    tasks = [
        asyncio.create_task(docker_status_task()),
        asyncio.create_task(gpu_task()),
        asyncio.create_task(cpu_ram_task()),
        asyncio.create_task(log_task()),
    ]
    try:
        while True:
            await ws.receive_text()  # el cliente no manda nada; solo detecta disconnect
    except WebSocketDisconnect:
        pass
    finally:
        for t in tasks:
            t.cancel()


async def _simulate_service(name: str, seconds: float, ok: bool, message: str) -> dict:
    await asyncio.sleep(seconds)
    return {"service": name, "ok": ok, "message": message}


@app.post("/boot")
async def boot() -> JSONResponse:
    # SIMULADO a propósito — no toca lifecycle/runner.py real. Ver docstring.
    plan = [
        ("llama-server", 2.0, True, "listo en 2s (simulado)"),
        ("understory", 1.0, True, "listo (simulado)"),
        ("pithagoras", 1.0, True, "listo (simulado)"),
    ]
    results = []
    for name, secs, ok, msg in plan:
        outcome = await _simulate_service(name, secs, ok, msg)
        results.append(outcome)
        if not outcome["ok"]:
            break  # boot corta en el primer fallo
    return JSONResponse({"results": results})


@app.post("/terminate")
async def terminate() -> JSONResponse:
    plan = [
        ("llama-server", 0.5, True, "detenido (simulado)"),
        ("understory", 0.5, True, "detenido (simulado)"),
        ("pithagoras", 0.5, True, "detenido (simulado)"),
    ]
    results = [await _simulate_service(name, secs, ok, msg) for name, secs, ok, msg in plan]
    return JSONResponse({"results": results})


@app.post("/capture")
async def capture() -> JSONResponse:
    # SIMULADO a propósito, mismo criterio que boot/terminate arriba — no
    # corre lifecycle/capture_profile.py real (no dispara llama-moe-trace
    # contra la GPU). Decisión de Tarkark 2026-09-16 (sesión 03 del
    # port-map); a diferencia de boot/terminate, todavía no hay sesión de
    # hardening que lo vuelva real (anotado en port-map.md).
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

    port = 8765  # spike: puerto fijo, distinto de los 3 servicios reales
    print(f"[daemon_spike] {time.strftime('%H:%M:%S')} arrancando en http://127.0.0.1:{port}")
    print(f"[daemon_spike] tail real de: {cfg.llama.log}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
