# Rinthel TUI

TUI (Textual) para gestionar el ciclo de vida de la infraestructura local de
Rinthel: un `llama-server` (Qwen3.6-35B-A3B, CUDA) más los stacks Docker de
**Understory** (capa de memoria MCP) y **Pithagoras** (portal de tareas).
Reemplaza los scripts bash previos (`rinthel-up.sh` / `rinthel-down.sh` /
`rinthel-reload.sh`) con fases `async` explícitas — ver
`rinthel_tui/lifecycle/`.

## Requisitos

- Python 3.13+
- Un build de `llama.cpp` con soporte CUDA (`llama-server`, y opcionalmente
  `llama-moe-trace` para capturar perfiles de ruteo MoE)
- El modelo GGUF que vayas a servir
- Docker + `docker compose` si vas a levantar Understory/Pithagoras
- Los repos de Understory y Pithagoras clonados en algún lado (paths
  configurables, ver [Configuración](#configuración))

## Instalación

**Modo dev** (recomendado si vas a tocar el código):

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

**Modo prod** (solo para usar el comando `rinthel`):

```bash
pip install .
```

## Uso

Con el venv de dev, desde la raíz del repo:

```bash
./rinthel-boot.sh
```

`rinthel-boot.sh` resuelve `.venv/bin/python` relativo a sí mismo — **hay que
ejecutarlo siempre desde (o con cwd en) la raíz del repo**; no está pensado
para symlinkearse ni copiarse a otro lugar.

Con una instalación vía `pip install .` (no requiere venv local ni cwd
específico):

```bash
rinthel
```

Ambos arrancan la misma `RinthelApp`: `SplashScreen` → `MenuScreen`, con las
opciones BOOT / RELOAD / TERMINATE / LOGS / CAPTURE / MONITOR.

## Configuración

Todos los paths, puertos y flags de inferencia de `llama-server` tienen un
default embebido en `rinthel_tui/config.py::default_config()` — pensados
para la máquina donde nació este repo. Para correrlo en otra máquina, copiá
`.env.example` a `.env` en la raíz del repo y descomentá/ajustá lo que
necesites:

```bash
cp .env.example .env
```

`.env` se carga automáticamente al importar `rinthel_tui.config` (vía
`python-dotenv`, buscando hacia arriba desde el cwd) y nunca se commitea
(está en `.gitignore`). Sin `.env`, el comportamiento es idéntico al
hardcodeado originalmente.

Variables disponibles: paths de binario/modelo/logs, puertos de
llama-server/Understory/Pithagoras, y todos los flags de inferencia
(`-c`, `--temp`, `--top-p`, `--n-cpu-moe`, `--threads`, etc.) — ver
`.env.example` para la lista completa con sus defaults.

Si `RINTHEL_LLAMA_BIN` o `RINTHEL_MODEL_PATH` apuntan a algo que no existe,
la app **no crashea al arrancar** — solo avisa por stderr. El fallo real (con
mensaje claro) ocurre recién si elegís BOOT y la fase de spawn de
llama-server falla de verdad.

`RINTHEL_EFFECTS=false` apaga los efectos visuales (glow/glitch/ripple) —
útil en terminales lentos o corriendo en CI.

## Troubleshooting

- **"error: no se encontró .venv/bin/python"** al correr `rinthel-boot.sh` —
  no creaste el venv, o lo estás corriendo desde otro directorio. Creá el
  venv en la raíz del repo (ver [Instalación](#instalación)).
- **Puerto ocupado** — BOOT no relanza `llama-server` si ya hay algo
  escuchando en `RINTHEL_PORT` (default `8080`); usa RELOAD o TERMINATE
  primero, o cambiá el puerto en `.env`.
- **"llama-server murió al instante"** — casi siempre un flag inválido o el
  modelo/bin no existen de verdad; revisá el log en `RINTHEL_LOG_PATH`
  (default `logs/llama-server.log`).
- **Modelo/binario no encontrado** — la app avisa por stderr al arrancar
  pero no bloquea el menú; ajustá `RINTHEL_LLAMA_BIN`/`RINTHEL_MODEL_PATH`
  en `.env`.
- **Docker daemon inactivo** — la fase de BOOT lo detecta y corta con
  instrucciones (`sudo systemctl start docker`) antes de tocar nada más.

## Desarrollo

`scripts/test_phases.py` corre fases individuales o listas completas contra
la infraestructura real, sin pasar por Textual — útil para probar cambios en
`lifecycle/` rápido:

```bash
.venv/bin/python scripts/test_phases.py list
.venv/bin/python scripts/test_phases.py boot
.venv/bin/python scripts/test_phases.py spawn_llama
.venv/bin/python scripts/test_phases.py wait_port_free --port 8080
```

No es un test suite de `pytest` (opera contra Docker/GPU reales, no hay
mocks) — es intencional que viva en `scripts/`, no en `tests/`.
