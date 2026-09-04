# Rinthel TUI

TUI (Textual) para gestionar el ciclo de vida de la infraestructura local de
Rinthel: un `llama-server` (CUDA) sirviendo **Qwen3.6-35B-A3B-MTP** más los stacks Docker
de **Understory** (capa de memoria MCP) y **Pithagoras** (portal de tareas).
El ciclo de vida se maneja en fases `async` explícitas — ver
`rinthel_tui/lifecycle/`.

## Instalación rápida (máquina nueva)

Un solo comando, sin más dependencia previa que poder instalar Python:

```bash
git clone <url-de-este-repo> && cd Rinthel-general && ./install.sh
```

`install.sh` detecta (o instala, vía PPA `deadsnakes` si hace falta) Python
3.13+, crea el venv y arranca la TUI. Desde ahí, **`[0] INSTALL`** en el menú
hace el resto: detecta GPU/CUDA/cmake/docker, clona y compila `llama.cpp` con
CUDA (arquitectura `native`, no una fija), descarga el modelo GGUF, y clona +
configura Pithagoras y Understory. Reglas:

- `NVIDIA driver` + `CUDA toolkit` deben estar instalados de antes —
  `[0] INSTALL` los detecta pero no los instala.
- Es re-ejecutable: cada fase es idempotente, omite lo que ya existe.
- `INSTALL` configura, no bootea — al terminar, usá `[1] BOOT` para levantar
  todo.

## Requisitos de hardware

- GPU NVIDIA con al menos **8 GB de VRAM** (para el offload CUDA de
  `llama-server`; el resto de las capas del modelo corre en CPU vía
  `--n-cpu-moe`, ajustable en `.env`).
- Al menos **32 GB de RAM**.

## Requisitos

- Python 3.13+
- Un build de `llama.cpp` con soporte CUDA (`llama-server`, y opcionalmente
  `llama-moe-trace` para capturar perfiles de ruteo MoE)
- El modelo GGUF — por defecto **Qwen3.6-35B-A3B-MTP** en cuantización
  `Q4_K_XL` (ver `.env.example` para otros modelos)
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
opciones INSTALL / BOOT / RELOAD / TERMINATE / LOGS / CAPTURE / MONITOR.

## Configuración

Todos los paths, puertos y flags de inferencia de `llama-server` tienen un
default embebido en `rinthel_tui/config.py::default_config()`. Para
ajustarlos a tu máquina, copiá `.env.example` a `.env` en la raíz del repo y
descomentá/ajustá lo que necesites:

```bash
cp .env.example .env
```

`.env` se carga automáticamente al importar `rinthel_tui.config` (vía
`python-dotenv`, buscando hacia arriba desde el cwd) y nunca se commitea
(está en `.gitignore`). Sin `.env`, se usan los defaults embebidos.

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

Vars específicas de `[0] INSTALL` (todas opcionales, ver `.env.example`):

- `RINTHEL_LLAMACPP_REPO_URL` / `RINTHEL_LLAMACPP_REPO_DIR` — de dónde se
  clona `llama.cpp` (branch `perf`) y dónde.
- `RINTHEL_MODEL_DOWNLOAD_URL` — de dónde se descarga el modelo GGUF si
  `RINTHEL_MODEL_PATH` todavía no existe.
- `RINTHEL_PITHAGORAS_REPO_URL` — de dónde se clona Pithagoras (branch
  `rinthel-pithagoras`).
- `RINTHEL_WORKSPACES_DIR` — carpeta que Pithagoras monta en `/workspaces`
  (default `$HOME`).

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

## Créditos

Tres piezas de infraestructura que `[0] INSTALL` levanta son de
[thecodacus](https://github.com/thecodacus):

- **Understory** (capa de memoria MCP) — corre desde la imagen publicada
  [`ghcr.io/thecodacus/understory`](https://github.com/thecodacus/understory),
  no se clona ni se compila desde fuente, ver
  `phase_install_setup_understory` en `rinthel_tui/lifecycle/install.py`.
- **Pithagoras** (portal de tareas) — se usa vía
  [`WilliamBarriga/pithagoras`](https://github.com/WilliamBarriga/pithagoras),
  fork basado en el original de thecodacus.
- El fork custom de **`llama.cpp`** (branch `perf`, default
  `RINTHEL_LLAMACPP_REPO_URL=https://github.com/thecodacus/llama.cpp.git`)
  que se clona y compila con soporte CUDA.

## Licencia

MIT — ver [`LICENSE`](LICENSE).
