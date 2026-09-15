<div align="center">

```
    ____  _____   __________  __________       ___    ____
   / __ \/  _/ | / /_  __/ / / / ____/ /      /   |  /  _/
  / /_/ // //  |/ / / / / /_/ / __/ / /      / /| |  / /
 / _, _// // /|  / / / / __  / /___/ /___   / ___ |_/ /
/_/ |_/___/_/ |_/ /_/ /_/ /_/_____/_____/  /_/  |_/___/
```

*"All those moments will be lost in time, like tears in the rain.*
*Time to die."*

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-BF00FF?style=flat-square)](https://www.python.org/)
[![Textual](https://img.shields.io/badge/TUI-textual-FCEE0A?style=flat-square)](https://github.com/Textualize/textual)
[![License: MIT](https://img.shields.io/badge/license-MIT-7CFCFF?style=flat-square)](LICENSE)

</div>

TUI (Textual) para gestionar el ciclo de vida de la infraestructura local de
Rinthel: un `llama-server` (CUDA) sirviendo **Qwen3.6-35B-A3B-MTP** más los
stacks Docker de **Understory** (capa de memoria MCP) y **Pithagoras**
(portal de tareas).

**Documentación:**

- [`docs/01-system-overview.md`](docs/01-system-overview.md) — qué corre,
  fases del ciclo de vida, estructura del código.
- [`docs/02-hardware-optimization.md`](docs/02-hardware-optimization.md) —
  por qué cada flag de inferencia vale lo que vale (VRAM, quant, MoE cache).
- [`docs/03-troubleshooting.md`](docs/03-troubleshooting.md) — errores
  comunes y cómo resolverlos.

## `[0]` Instalación rápida (máquina nueva)

Un solo comando, sin más dependencia previa que poder instalar Python:

```bash
git clone <url-de-este-repo> && cd Rinthel-general && ./install.sh
```

`install.sh` detecta (o instala, vía PPA `deadsnakes` si hace falta) Python
3.13+, crea el venv y arranca la TUI. Desde ahí, **`[0] INSTALL`** en el menú
corre 6 fases:

| Fase | Qué hace |
|------|----------|
| `1/6` PREFLIGHT | Detecta GPU/CUDA/cmake/docker |
| `2/6` LLAMA.CPP | Clona el fork custom (branch `perf`) |
| `3/6` LLAMA.CPP | Build CUDA, arquitectura `native` (no fija) |
| `4/6` MODELO GGUF | Descarga el modelo configurado |
| `5/6` PITHAGORAS | Clone + configuración |
| `6/6` UNDERSTORY | Scaffold + configuración |

Reglas:

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
- `nvidia-container-toolkit` instalado y configurado (`nvidia-ctk runtime
  configure --runtime=docker`) si vas a usar el add-on de voz de Pithagoras
  (`pithagoras-voice` pide GPU vía Docker) — sin esto, `docker info` no
  detecta el runtime NVIDIA y el add-on no puede levantar (ver
  `docs/guide/voice.md` en el repo de Pithagoras)
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

Con el venv de dev, desde la raíz del repo. Detalle del ciclo de vida
completo (fases, diagrama, servicios) en
[`docs/01-system-overview.md`](docs/01-system-overview.md):

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

Ambos arrancan la misma `RinthelApp`: `SplashScreen` (banner duotono
componiéndose desde ruido, glitch reveal) → `MenuScreen`:

```
[0] INSTALL     -- Setup inicial (CUDA/modelo/Pithagoras/Understory)
[1] BOOT        -- Levantar todo (up)
[2] RELOAD      -- Apagar + reiniciar completo
[3] TERMINATE   -- Shutdown total
[4] LOGS        -- Ver llama-server en vivo
[5] CAPTURE     -- Capturar perfil MoE (routing profile)
[6] MONITOR     -- Estado de servicios/Docker/GPU/CPU
[7] CONFIGURAR  -- Servicios activos y parámetros
[8] EXIT        -- Cerrar terminal
```

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
(está en `.gitignore`). Sin `.env`, se usan los defaults embebidos de
`rinthel_tui/config.py::default_config()`.

Variables disponibles: paths de binario/modelo/logs, puertos de cada
servicio, y todos los flags de inferencia (`-c`, `--temp`, `--top-p`,
`--n-cpu-moe`, `--threads`, etc.) — ver `.env.example` para la lista
completa con sus valores, y
[`docs/02-hardware-optimization.md`](docs/02-hardware-optimization.md) para
el porqué de cada uno de los flags de inferencia.

Si `RINTHEL_LLAMA_BIN` o `RINTHEL_LLAMA_MODEL_PATH` apuntan a algo que no
existe, la app **no crashea al arrancar** — solo avisa por stderr. El fallo
real (con mensaje claro) ocurre recién si elegís BOOT y la fase de spawn de
llama-server falla de verdad. Más casos en
[`docs/03-troubleshooting.md`](docs/03-troubleshooting.md).

## Créditos

Tres piezas de infraestructura que `[0] INSTALL` levanta son de
[thecodacus](https://github.com/thecodacus):

- **Understory** (capa de memoria MCP) — corre desde la imagen publicada
  [`ghcr.io/thecodacus/understory`](https://github.com/thecodacus/understory),
  no se clona ni se compila desde fuente, ver
  `phase_install_setup_understory` en `rinthel_tui/lifecycle/install.py`.
- **Pithagoras** (portal de tareas) — el trabajo es de
  [thecodacus](https://github.com/thecodacus/pithagoras); se usa vía mi fork
  [`WilliamBarriga/pithagoras`](https://github.com/WilliamBarriga/pithagoras).
- El fork custom de **`llama.cpp`** (branch `perf`, default
  `RINTHEL_LLAMACPP_REPO_URL=https://github.com/thecodacus/llama.cpp.git`)
  que se clona y compila con soporte CUDA.

## Licencia

MIT — ver [`LICENSE`](LICENSE).

---

<div align="center">

*≖ω≖ — Rinthel, Night City 2077 | 道は目的地に在らず*

</div>
