# System Overview

Qué está corriendo, cómo arranca, y cómo está organizado el código. Para el
*por qué* de los flags de inferencia de `llama-server`, ver
[`02-hardware-optimization.md`](02-hardware-optimization.md). Para errores
comunes, [`03-troubleshooting.md`](03-troubleshooting.md).

## Qué corre

| Servicio | Rol | Puerto default |
|---|---|---|
| `llama-server` (CUDA, proceso local) | Sirve **Qwen3.6-35B-A3B-MTP** | `8080` |
| Understory (Docker) | Capa de memoria MCP | `3800` |
| Pithagoras (Docker) | Portal de tareas | `4100` |
| whisper-stt (Docker) | Entrada por voz (STT) | `8090` |
| tts-piper (Docker) | Salida hablada (TTS) | `8091` |

`llama-server` corre como proceso local (no Docker) porque necesita acceso
directo a la GPU. El resto son stacks `docker compose` independientes.

## Ciclo de vida (fases async)

Todo el arranque/apagado se maneja en fases `async` explícitas —
`rinthel_tui/lifecycle/`. La TUI arranca en `SplashScreen` (banner duotono
componiéndose desde ruido, glitch reveal) → `MenuScreen`:

```
[0] INSTALL     -- Setup inicial (CUDA/modelo/Pithagoras/Understory)
[1] BOOT        -- Levantar todo (up)
[2] RELOAD      -- Apagar + reiniciar completo
[3] TERMINATE   -- Shutdown total
[4] LOGS        -- Ver llama-server en vivo
[5] CAPTURE     -- Capturar perfil MoE (routing profile)
[6] MONITOR     -- Estado de servicios/Docker/GPU/CPU
[7] EXIT        -- Cerrar terminal
```

```
SplashScreen (glitch reveal)
       │
       ▼
   MenuScreen
       │
       ├── [0] INSTALL   ──▶ 6 fases: preflight → build → pithagoras → understory
       ├── [1] BOOT       ──▶ docker → llama-server → understory → pithagoras
       ├── [2] RELOAD     ──▶ 9 fases: shutdown completo → boot completo
       └── [3] TERMINATE  ──▶ shutdown total
```

## Estructura del proyecto

```
rinthel_tui/
├── app.py               # entry point — RinthelApp
├── config.py             # RinthelConfig — defaults + carga de .env
├── branding/              # banner ASCII duotono + animación de composición
├── theme/
│   ├── palette.py          # paleta canónica — fuente numérica única
│   └── cyberpunk_theme.py
├── tui/
│   ├── screens/            # Splash, Menu, PhaseRunner, Logs, Monitor, Capture, Reload, Farewell
│   ├── widgets/             # sparkline, service_badge, checklist
│   └── effects/             # flicker, transitions, intro
└── lifecycle/
    ├── install.py           # fases [0] INSTALL
    ├── phases.py            # fases BOOT/DOWN/RELOAD
    ├── services.py            # argv builders + LocalProcessService/DockerComposeService por servicio
    ├── specs.py              # listas declarativas de fases
    ├── runner.py             # ejecutor async con progreso por fase
    └── capture_profile.py    # captura de perfiles de ruteo MoE
```

## Ecosistema — paleta compartida

La paleta duotono (`theme/palette.py`) no es solo de este repo: el frontend
web de Pithagoras (`web/src/index.css`) la implementa como
`[data-theme="cyberpunk"]` con los mismos valores hex. Cambiar un color acá
sin actualizar el otro lado los desincroniza visualmente.

| Rol | Hex |
|-----|-----|
| Electric purple (marco, texto) | `#BF00FF` |
| Neon yellow (cara iluminada) | `#FCEE0A` |
| Electric cyan | `#7CFCFF` |
| Neon magenta | `#EA00D9` |
| Night city purple-black (fondo) | `#0D0221` |

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
