# Protocolo daemon↔cliente: un WebSocket para telemetría, REST bloqueante para comandos

El daemon Python (FastAPI) y el cliente Rust (Ratatui) necesitan un límite de proceso donde hoy no hay ninguno (todo in-process vía Textual). Se evaluaron JSON-RPC/gRPC sobre socket Unix contra WebSocket/REST sobre TCP localhost; se eligió lo segundo.

Decidimos: un único WebSocket (`/ws/monitor`) multiplexa los cuatro streams en vivo (estado docker, GPU, CPU/RAM, log de llama-server) con un sobre `{"type", "data"}` por mensaje — una sola conexión y un solo loop de reconexión en vez de cuatro. Los comandos `boot`/`terminate` son `POST` bloqueantes (esperan a que termine la secuencia completa, hasta ~90s+), no fire-and-forget, porque Rinthel es monousuario y la espera es aceptable a cambio de saber al toque si algo falló. `GET /theme` es un fetch único al arrancar el cliente, fuera del túnel, porque no cambia en runtime. Bind TCP en `127.0.0.1` (consistente con los tres servicios existentes) en vez de socket Unix. Schema: modelos Pydantic del lado Python, structs `serde` escritos a mano del lado Rust — sin codegen, por ser un conjunto chico de mensajes (~7 formas) y no meter una herramienta más al primer proyecto Rust en serio de Tarkark. Reconexión del WebSocket es sin replay: estado fresco al reconectar, igual que hoy `LogTail`/`Sparkline` al remontar una screen.

Se descartó gRPC/JSON-RPC sobre socket Unix por ser más pesado (tooling de protobuf, o un framework JSON-RPC) para un daemon local de un solo usuario sin necesidad de auth/TLS — FastAPI + WebSocket estándar es más legible y tiene menos curva para alguien recién empezando con Rust.

Ver [.scratch/ratatui-migration/issues/03-fastapi-protocol-design.md](../../.scratch/ratatui-migration/issues/03-fastapi-protocol-design.md) para las formas exactas de mensaje.

## Amendment (sesión 05 del port-map, 2026-09-16): progreso en vivo de boot/terminate por WS

`POST /boot`/`POST /terminate` siguen siendo bloqueantes y su respuesta (`{"results": [ServiceOutcome]}`) sigue siendo la única fuente de verdad — esto no cambia. Lo que se agrega es telemetría adicional por `/ws/monitor` mientras la secuencia corre, para que el cliente pueda pintar un checklist/log en vivo (paridad con `PhaseChecklist`/`ScreenPhaseReport` del lado Textual, que sí actualizaban en vivo por estar in-process) en vez de solo un resumen post-hoc:

- `phase_status`: `{"label": str, "status": "running"|"done"|"error"}` por cada `PhaseSpec` (granularidad de `boot_phases()`/`down_phases()`, no de `boot_units`/`down_units`).
- `phase_log`: `{"kind": "info"|"success"|"warn"|"error", "message": str}` por cada llamada a `report.*` dentro de una fase.

Decisión explícita de Tarkark: construir este canal ahora en vez de dejarlo pendiente — la alternativa (checklist "resuelto de una vez" al llegar la respuesta del POST, sin fila por fila en vivo) quedaba coja frente al widget que se estaba porteando. Fire-and-forget (`asyncio.create_task`, sin awaitear): son mensajes de progreso para la UI, no el resultado — no hay corrección que proteger si uno se pierde. Sin cliente conectado, el broadcast es un no-op.
