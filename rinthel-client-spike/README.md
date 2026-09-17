# SPIKE — cliente Ratatui (ticket 05)

Prototipo throwaway, no producción. Valida el diseño de los tickets 01-04 del
mapa [Ratatui TUI Migration](../.scratch/ratatui-migration/map.md) contra un
cliente y un daemon reales. Vive en la rama `spike/ratatui-mvp-05`.

## Qué es cada parte

- **Daemon** — `../rinthel_tui/daemon.py` (promovido desde `daemon_spike.py`
  en sesión 04 del port-map). FastAPI, reusa de verdad
  `monitoring/resources.py` (GPU/CPU/RAM), `monitoring/services.py` (docker
  ps) y `theme/palette.py` — todo de solo lectura. `boot`/`terminate` corren
  `lifecycle/runner.py` **real** (arrancan/matan llama-server, Understory y
  Pithagoras de verdad). `capture` sigue **simulado** (sin sesión de
  hardening asignada todavía).
- **Cliente** — este directorio, `rinthel-client-spike`. Ratatui + tokio +
  `tokio-tungstenite` (WebSocket) + `reqwest` (REST) + `ratatui-sci-fi`
  (tema Cyberpunk, widget `EnergyGauge`).

## Correrlo (paso a paso — primera vez con Rust)

1. **Rust ya está instalado** en este container (`rustup` corrido en esta
   sesión: `rustc 1.98.1`). Si abrís una terminal nueva y `cargo` no
   aparece, corré `source "$HOME/.cargo/env"` (o abrí una shell nueva —
   `rustup` ya dejó eso en `~/.bashrc`... si no aparece, avisame).

2. **Levantar el daemon** (deja la terminal ocupada, corre en foreground):
   ```bash
   cd ~/Rinthel-general
   .venv/bin/python -m rinthel_tui.daemon
   ```
   Imprime el puerto (8765) y el archivo de log que está taileando. `Ctrl+C`
   para pararlo.

3. **En otra terminal, correr el cliente**:
   ```bash
   cd ~/Rinthel-general/rinthel-client-spike
   source "$HOME/.cargo/env"
   cargo run
   ```
   La primera vez compila todas las dependencias (~1 min). Las siguientes
   son instantáneas (cache incremental de `cargo`, en `target/`).

## Qué mirar / probar

- **Menú**: `↑`/`↓` para moverse, `Enter` para elegir. `MONITOR` entra a la
  pantalla de métricas.
- **Monitor**: badges de Understory/Pithagoras (llama-server queda "N/A" en
  el spike — no tiene contenedor Docker, su badge real necesitaría un ping a
  su `ready_url`, fuera de alcance acá). Fila de `EnergyGauge` (ratatui-sci-fi,
  tema Cyberpunk) al lado de los `Sparkline` de historial (ratatui puro,
  coloreado con la paleta que sirve `GET /theme`) — son dos caminos
  distintos al mismo dato, para comparar estética con estética.
  Tabla docker + tail de `logs/llama-server.log` en vivo.
  `b` = boot, `t` = terminate (reales desde sesión 04 — arrancan/matan
  llama-server, Understory y Pithagoras de verdad, bloqueante hasta ~90s+ si
  llama-server tarda en cargar el modelo), `Esc` = volver al menú, `q` =
  salir.
- **Matá el daemon con el cliente abierto**: el cliente debería quedarse
  vivo y reconectar solo cuando lo levantes de nuevo (sin replay — estado
  fresco, tal como decidió el ticket 03/ADR 0001).

## Lo que esto ya validó (para la reacción)

- Las 4 formas de mensaje del WebSocket y las 2 del REST (ticket 03 / ADR
  0001) redondean bien Python→JSON→Rust con structs `serde` escritos a
  mano — sin fricción, tal como preveía la decisión de "sin codegen".
  Un bug real que atrapó esto: mi primer intento reusaba el mismo struct
  `Palette` para `canonical` y `extended` de `/theme` — son formas
  distintas, el cliente paniqueó al deserializar hasta que separé los tipos.
- El streaming real (GPU vía `nvidia-smi`, CPU/RAM vía `psutil`, docker vía
  `docker compose ps`, log vía tail real de `llama-server.log`) llega
  al cliente sin problema aparente de latencia — a ojo, no se siente peor
  que Textual hoy (falta que lo confirmes vos con el cliente corriendo).
- `ratatui-sci-fi::EnergyGauge` trae su propia cascada CSS *interna*: alcanza
  con `.theme(Theme::Cyberpunk)`, no hace falta tocar `ratatui-style` a mano
  para tener color-por-nivel (ok/warn/alert) automático. Esto le saca bastante
  incertidumbre al ítem de "Not yet specified" sobre viabilidad del CSS
  cascade — al menos para widgets que, como `EnergyGauge`, embeben su propia
  hoja de estilos.
- `ratatui-sci-fi` + `ratatui-style` (`=0.2.1`/`=0.2.0`, versión fijada per
  ticket 01) compilan sin conflicto de versiones junto a `tokio`/`reqwest`/
  `ratatui 0.30.2` en el mismo binario.

## Simplificaciones deliberadas (no son bugs, son alcance de spike)

- Badge de `llama-server` no está wireado (no hay contenedor Docker que
  chequear con el `docker_status` que ya existe).
- No hay reconexión visible en pantalla (el cliente reconecta solo, pero no
  hay un indicador de "reconectando..." — se nota por el `log_tail`
  quedándose quieto).
- El menú tiene solo 4 opciones (recorte del ticket 02); no hay `settings`,
  `logs`, `capture`, `farewell`, `install`, ni efectos.
