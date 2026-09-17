# Rinthel

TUI de gestión de lifecycle para Rinthel/Understory/Pithagoras. Capa visual en migración de Textual (Python, in-process) a Ratatui (Rust) detrás de un límite de proceso — ver `.scratch/ratatui-migration/`.

## Language

**Managed service**:
Uno de los tres servicios que el daemon controla como unidad de lifecycle: `llama-server` (proceso local) o Understory/Pithagoras (docker compose). El código las modela como `LocalProcessService`/`DockerComposeService` (`lifecycle/managed_service.py`).
_Avoid_: proceso, contenedor (son el mecanismo de una managed service, no sinónimos — Understory es una managed service aunque por dentro sea un contenedor Docker).

**Boot** / **Terminate**:
Los dos comandos de lifecycle expuestos por el protocolo daemon↔cliente: boot lleva las tres managed services arriba, terminate las lleva abajo. Boot corta en el primer fallo (las fases siguientes asumen que la anterior funcionó); terminate sigue con las que quedan aunque una falle (no dejar nada corriendo por error).
_Avoid_: start/stop, up/down — usar boot/terminate de forma consistente en protocolo y UI.

**Service outcome**:
El resultado de una managed service dentro de una respuesta de boot/terminate: si terminó bien y un mensaje humano-legible. Una lista ordenada de service outcomes es la respuesta completa de boot/terminate.

**Telemetry stream**:
Uno de los cuatro flujos en vivo que el daemon empuja al cliente por el túnel de monitoreo: estado docker, muestra de GPU, muestra de CPU/RAM, línea de log. Cada mensaje del túnel lleva un tag que identifica a cuál stream pertenece.
_Avoid_: evento, update genérico — cada stream tiene una identidad propia (no son intercambiables).
