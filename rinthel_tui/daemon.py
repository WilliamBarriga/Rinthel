"""Daemon FastAPI de Rinthel — infraestructura persistente e independiente
del cliente (ver issues/04-packaging-entrypoint.md: el daemon Python es lo
que sobrevive entre sesiones de la TUI, el binario Rust es el cliente
reemplazable).

Nace como ``daemon_spike.py`` (ticket "Construir el spike MVP",
.scratch/ratatui-migration/issues/05-mvp-spike.md) para validar el
protocolo diseñado en el ticket 03 (docs/adr/0001-daemon-protocol-shape.md)
contra un cliente Ratatui real. Sesión 04 del port-map lo promueve acá y
reemplaza el boot/terminate simulado por llamadas reales a
``lifecycle/runner.py`` + ``lifecycle/specs.py``.

Corré con:  .venv/bin/python -m rinthel_tui.daemon   (o el entry point
``rinthel-daemon``, ver pyproject.toml)

``/capture`` sigue SIMULADO a propósito (mismo motivo que tenía boot/
terminate antes de esta sesión) — no hay todavía una sesión de hardening
que lo vuelva real (ver "Not yet specified" en port-map.md). Todo lo demás
(GPU, CPU/RAM, docker ps, tail de log) es de solo lectura contra el sistema
real, sin cambios respecto al spike original.

Sesión 06 agrega ``/reload`` — puerto real de ``ReloadScreen``
(``rinthel_tui/tui/screens/reload.py``), mismo mecanismo bloqueante +
``phase_status``/``phase_log`` que boot/terminate, corriendo las 3 tandas
de ``specs.reload_units`` (shutdown → boot → rebuild) en secuencia y
cortando en el primer fallo.

Sesión 10 agrega ``phase_batch`` (amendment de docs/adr/0001): grillado con
Tarkark — las 2 transiciones entre tandas que el cliente retrofitea
(``DatamoshEffect``/``VignetteEffect``) necesitan saber cuándo termina
"shutdown" y empieza "boot", y cuándo termina "boot" y empieza "rebuild";
sin eso no tenían de dónde dispararse (`/reload` corre las 3 tandas de un
tirón, sin ningún marcador de límite). ``{"batch": "boot"|"rebuild"}``, uno
antes de cada una de esas 2 tandas — ``"shutdown"`` no se emite (nada la
escucha, no hay transición antes de la primera tanda).

Sesión 07 agrega ``/install`` — puerto de ``[0] INSTALL`` (`menu.py`), mismo
mecanismo bloqueante + phase_status/phase_log, corriendo ``specs.
install_units`` (PREFLIGHT + una unidad por ``InstallUnit`` habilitada) y
cortando en el primer fallo. A diferencia de boot/terminate/reload, esto
corre subprocesos reales (git clone, build de CUDA, descarga del modelo)
desde el día uno — no hay versión simulada de install (a diferencia de
capture, que sí la tiene).

Sesión 05 (phase_runner) agrega dos tipos de sobre a ``/ws/monitor``, para
que el checklist/log en vivo de BOOT/TERMINATE tenga de dónde sacar
progreso sin romper ADR 0001 (``/boot``/``/terminate`` siguen siendo POST
bloqueantes y su respuesta sigue siendo la fuente de verdad; el WS es
telemetría best-effort, igual que docker_status/gpu_sample/etc.):

- ``phase_status``: ``{"label": str, "status": "running"|"done"|"error"}``
  — un mensaje por cada ``PhaseSpec`` que corre ``run_phase_list``, vía su
  parámetro ``on_phase`` (ver lifecycle/runner.py). Misma granularidad fina
  que ``boot_phases()``/``down_phases()`` (spawn y wait son filas
  separadas), no la agrupación por servicio de ``boot_units``/``down_units``
  que sí usa la respuesta final.
- ``phase_log``: ``{"kind": "info"|"success"|"warn"|"error", "message": str}``
  — un mensaje por cada llamada a ``report.info/success/warn/error`` dentro
  de una fase, para el panel de log en vivo (mismo rol que ``ScreenPhaseReport``
  tenía del lado Textual).

Fire-and-forget a propósito (``asyncio.create_task``, no awaited): son
mensajes de progreso para la UI, no el resultado — perder uno (cliente
desconectado a mitad de un boot) no afecta el ``ServiceOutcome`` final que
sigue viajando por la respuesta del POST. Sin cliente conectado a
``/ws/monitor``, `broadcast` no hace nada (set vacío).

Sesión 09 agrega ``GET``/``POST /config`` — puerto de ``[N] CONFIGURAR``
(``rinthel_tui/tui/screens/settings.py``). Grillado con Tarkark 2026-09-16:
el daemon pasa a ser dueño de toda la config (``RinthelConfig`` completo,
las 5 sub-configs incluyendo ``install``); el cliente Rust no duplica
``config._ENTRIES`` ni parsea ``.env``. ``GET /config`` es un fetch único
fuera del túnel WS (mismo criterio que ``GET /theme``: no cambia en
runtime salvo que el usuario lo edite) y devuelve un shape genérico —
``{"services": [{"attr", "display_name", "enabled", "fields": [{"attr",
"env", "kind", "group", "value"}, ...]}, ...]}`` — en vez de un struct fijo
por sub-config: mismo espíritu "genérico a propósito" que ya tenía
``settings.py`` (agregar un ``Field`` en ``config.py`` lo hace aparecer acá
solo, sin tocar el daemon ni el cliente Rust). ``enabled`` es ``None``
para sub-configs sin ese campo (``moe``/``install`` no son un
``LocalProcessService``/``DockerComposeService``, no tienen on/off).
``value``/``kind`` reusan ``config.stringify``/``config.KIND_NAMES`` — el
valor viaja como string (igual que un ``Input`` de Textual), el cliente
decide qué widget pintar según ``kind`` ("bool"→checkbox, resto→input).

``POST /config`` recibe ``{"overrides": {<env var>: <string>, ...}}``
(mismo shape que ``config.diff_overrides``/``env_file.update_env_file``).
A diferencia de la screen Textual original (que nunca validaba antes de
guardar), acá sí: arma un ``RinthelConfig`` hipotético con
``config.with_overrides`` y corre ``.validate()`` antes de escribir — si
salta ``ConfigError`` (puertos duplicados/inválidos, numéricos ≤0), no
toca el ``.env`` y devuelve los errores. Si el write sale bien, ``cfg``
(el módulo-global, no solo el archivo) se reemplaza en el momento por el
``RinthelConfig`` ya validado — corrección post-prueba-en-vivo (sesión 09):
la primera versión dejaba ``cfg`` congelado hasta el próximo restart del
daemon completo, lo que además de dejar ``GET /config`` mostrando el valor
viejo, hacía que "revertir" un campo a su valor original vía la UI
comparara contra ese mismo valor viejo y no escribiera nada — silencioso y
confuso. Con el fix: un `BOOT`/`RELOAD` posterior a un `GUARDAR` ya usa los
valores nuevos sin reiniciar el daemon (el proceso ya corriendo de
llama-server/etc. no se toca retroactivamente, como es esperable — el
cambio aplica en el próximo *spawn*, no en caliente sobre un proceso vivo).
No hay watching del `.env` en disco: un cambio hecho por fuera de
`POST /config` (edición manual del archivo) sigue necesitando reiniciar el
daemon para que `cfg` lo vea.

Sesión 08 agrega ``llama_status`` — mismo patrón periódico que
``docker_status``/``gpu_sample``/``cpu_ram_sample`` (un task que manda y
duerme en loop mientras dure la conexión), no el trío phase_status/phase_log
de arriba (eso es telemetría de una corrida puntual; esto es un estado
parado que existe siempre que haya un cliente conectado, corriendo BOOT o
no). ``{"ready": bool}`` — un solo GET puntual (``managed_service.check_ready``,
sin backoff) contra el mismo ``ready_url_of`` que ya usa ``phase_wait_ready``
en boot/reload: en llama-server (llama.cpp), ese endpoint queda detrás de un
único gate de "server listo" que solo se levanta después de cargar el modelo
(confirmado en el propio server.cpp) — así que "ready" ya significa server
arriba + modelo cargado, no hace falta un segundo chequeo.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from rinthel_tui import config
from rinthel_tui.config import ConfigError, default_config
from rinthel_tui.env_file import update_env_file
from rinthel_tui.lifecycle import phases, specs
from rinthel_tui.lifecycle.managed_service import check_ready
from rinthel_tui.lifecycle.services import (
    DOCKER_SERVICES,
    LLAMA_SERVICE,
    LOCAL_SERVICES,
    PITHAGORAS_SERVICE,
    UNDERSTORY_SERVICE,
)
from rinthel_tui.lifecycle.runner import PhaseFailed, run_phase_list
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

# display_name de cada sub-config con instancia de servicio real — moe/install
# no tienen una (no son LocalProcessService/DockerComposeService), caen al
# fallback `attr.upper()` en `_config_payload`.
_CONFIG_DISPLAY_NAMES = {
    "llama": LLAMA_SERVICE.display_name,
    "understory": UNDERSTORY_SERVICE.display_name,
    "pithagoras": PITHAGORAS_SERVICE.display_name,
}

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


def _config_payload() -> dict:
    """Shape genérico de ``GET /config`` — ver docstring del módulo. Itera
    ``config._ENTRIES`` en vez de listar sub-configs a mano, así que sumar
    un ``Field``/sub-config nuevo en ``config.py`` alcanza para que aparezca
    acá sin tocar el daemon."""
    services = []
    for attr, fields in config._ENTRIES:
        sub = getattr(cfg, attr)
        enabled_field = next((f for f in fields if f.attr == "enabled"), None)
        services.append(
            {
                "attr": attr,
                "display_name": _CONFIG_DISPLAY_NAMES.get(attr, attr.upper()),
                "enabled": getattr(sub, "enabled") if enabled_field else None,
                # env var del toggle — separado de "enabled" porque el
                # cliente lo necesita para armar el override al tildar/
                # destildar (mismo dict env->string que el resto de POST
                # /config), y no está en "fields" (se filtra abajo).
                "enabled_env": enabled_field.env if enabled_field else None,
                "fields": [
                    {
                        "attr": f.attr,
                        "env": f.env,
                        "kind": config.KIND_NAMES[f.kind],
                        "group": f.group,
                        "value": config.stringify(getattr(sub, f.attr)),
                    }
                    for f in fields
                    if f.attr != "enabled"  # ya sale en el "enabled" de arriba
                ],
            }
        )
    return {"services": services}


@app.get("/config")
def get_config() -> JSONResponse:
    return JSONResponse(_config_payload())


@app.post("/config")
async def post_config(payload: dict) -> JSONResponse:
    # Actualiza `cfg` en memoria tras un write propio (no watching del
    # archivo — un cambio externo al .env todavía requiere reiniciar el
    # daemon). Sin esto, un GET inmediatamente después de guardar seguía
    # mostrando el valor viejo, y peor: "revertir" un campo a su valor
    # original vía la UI quedaba comparado contra el propio valor viejo de
    # `cfg` y no escribía nada (encontrado en vivo, sesión 09 del port-map).
    global cfg
    edits = payload.get("overrides", {})
    to_write = config.diff_overrides(cfg, edits)
    if not to_write:
        return JSONResponse({"ok": True, "written": 0, "warnings": []})
    try:
        updated = config.with_overrides(cfg, to_write)
        warnings = updated.validate()
    except ConfigError as e:
        return JSONResponse({"ok": False, "written": 0, "errors": str(e).split("; ")})
    update_env_file(_ENV_PATH, to_write, seed_from=_ENV_EXAMPLE_PATH)
    cfg = updated
    return JSONResponse({"ok": True, "written": len(to_write), "warnings": warnings})


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


@dataclass
class _Collected:
    """``PhaseReport`` que junta los mensajes terminales (success/warn/error)
    de una unidad de servicio en un solo ``ServiceOutcome`` — ver
    docs/adr/0001. ``info()`` se descarta a propósito: es ruido de proceso
    (stdout de ``docker compose``, hints supletorios como el de
    ``on_timeout_hint``), no el resultado en sí; cada fase de
    ``managed_service.py`` siempre termina con un success/warn/error real,
    así que no se pierde la señal que importa. Decisión de Tarkark (sesión
    04 del port-map): concatenar en vez de quedarse con el último mensaje —
    spawn y wait son eventos distintos y los dos aportan contexto."""

    ok: bool = True
    messages: list[str] = field(default_factory=list)

    def info(self, msg: str) -> None:
        pass

    def success(self, msg: str) -> None:
        self.messages.append(msg)

    def warn(self, msg: str) -> None:
        self.messages.append(msg)

    def error(self, msg: str) -> None:
        self.ok = False
        self.messages.append(msg)


@dataclass
class _BroadcastingCollected(_Collected):
    """``_Collected`` + un ``phase_log`` por ``/ws/monitor`` en cada llamada
    — a diferencia de ``_Collected.info()``, acá sí se transmite (es ruido
    para el ``message`` final del ``ServiceOutcome``, pero es justo lo que
    ``ScreenPhaseReport`` mostraba en vivo del lado Textual). Broadcast es
    fire-and-forget (ver docstring del módulo); las llamadas base siguen
    alimentando ``ok``/``messages`` sin cambios."""

    def info(self, msg: str) -> None:
        super().info(msg)
        asyncio.create_task(broadcast("phase_log", {"kind": "info", "message": msg}))

    def success(self, msg: str) -> None:
        super().success(msg)
        asyncio.create_task(broadcast("phase_log", {"kind": "success", "message": msg}))

    def warn(self, msg: str) -> None:
        super().warn(msg)
        asyncio.create_task(broadcast("phase_log", {"kind": "warn", "message": msg}))

    def error(self, msg: str) -> None:
        super().error(msg)
        asyncio.create_task(broadcast("phase_log", {"kind": "error", "message": msg}))


async def _on_phase(spec: PhaseSpec, status: str) -> None:
    await broadcast("phase_status", {"label": spec.label, "status": status})


async def _run_unit(service: str, unit_specs: list[PhaseSpec]) -> dict:
    collected = _BroadcastingCollected()
    try:
        await run_phase_list(cfg, unit_specs, collected, on_phase=_on_phase)
    except PhaseFailed:
        pass  # collected.ok ya quedó en False vía report.error
    return {
        "service": service,
        "ok": collected.ok,
        "message": " — ".join(collected.messages) or "sin mensaje",
    }


@app.post("/boot")
async def boot() -> JSONResponse:
    results = [await _run_unit("docker", [PhaseSpec("◈ DOCKER", phases.phase_check_docker)])]
    if results[0]["ok"]:
        for service, unit_specs in specs.boot_units(cfg):
            outcome = await _run_unit(service, unit_specs)
            results.append(outcome)
            if not outcome["ok"]:
                break  # boot corta en el primer fallo
    return JSONResponse({"results": results})


@app.post("/terminate")
async def terminate() -> JSONResponse:
    results = [await _run_unit(service, unit_specs) for service, unit_specs in specs.down_units(cfg)]
    return JSONResponse({"results": results})


@app.post("/reload")
async def reload() -> JSONResponse:
    # Sesión 06 del port-map: shutdown → DOCKER → boot(solo local) →
    # rebuild(solo docker, no_cache) — mismo trío phase_status/phase_log
    # que boot/terminate, corta en el primer fallo (grillado con Tarkark:
    # mismo criterio que /boot, replica _run_all de reload.py). Sesión 10:
    # un ``phase_batch`` antes de "boot" y antes de "rebuild" — ver
    # docstring del módulo — para que el cliente sepa cuándo disparar
    # Datamosh/Vignette (las 2 transiciones entre tandas de reload.py que
    # antes no tenían de dónde engancharse).
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
            outcome = await _run_unit(service, unit_specs)
            results.append(outcome)
            if not outcome["ok"]:
                return JSONResponse({"results": results})
    return JSONResponse({"results": results})


async def _simulate_service(name: str, seconds: float, ok: bool, message: str) -> dict:
    await asyncio.sleep(seconds)
    return {"service": name, "ok": ok, "message": message}


@app.post("/install")
async def install() -> JSONResponse:
    # Sesión 07 del port-map: mismo mecanismo bloqueante + phase_status/
    # phase_log que boot/terminate/reload (grillado con Tarkark, ver ticket
    # 07 — install no necesita un endpoint genérico "correr lista de
    # fases": install_units ya agrupa por InstallUnit igual que boot_units).
    # Corta en el primer fallo: si PREFLIGHT falla (falta CUDA/docker) no
    # tiene sentido seguir con clone/build/descarga.
    results = []
    for service, unit_specs in specs.install_units(cfg):
        outcome = await _run_unit(service, unit_specs)
        results.append(outcome)
        if not outcome["ok"]:
            break
    return JSONResponse({"results": results})


@app.post("/capture")
async def capture() -> JSONResponse:
    # SIMULADO a propósito — a diferencia de boot/terminate (ya reales desde
    # sesión 04), capture todavía no tiene sesión de hardening asignada (ver
    # "Not yet specified" en port-map.md). No corre lifecycle/capture_profile.py
    # real (no dispara llama-moe-trace contra la GPU).
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
    # overrideable por `.env` (sesión 11 del port-map: `rinthel-boot.sh` lo
    # lee de ahí y se lo pasa al binario Rust como `--port`, mismo default
    # 8765 de siempre si nadie lo setea).
    port = int(os.getenv("RINTHEL_DAEMON_PORT", "8765"))
    print(f"[daemon] {time.strftime('%H:%M:%S')} arrancando en http://127.0.0.1:{port}")
    print(f"[daemon] tail real de: {cfg.llama.log}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
