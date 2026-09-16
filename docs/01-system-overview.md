# System Overview

What's running, how it boots, and how the code is organized. For the
*why* behind `llama-server`'s inference flags, see
[`02-hardware-optimization.md`](02-hardware-optimization.md). For common
errors, see [`03-troubleshooting.md`](03-troubleshooting.md).

See also: [runtime architecture diagram](diagrams/out/rinthel-runtime.html)
and [install/build sources diagram](diagrams/out/rinthel-install-sources.html)
(interactive — open the `.html` in a browser; generated with
[Archify](https://github.com/tt-a1i/archify) from
`docs/diagrams/*.eraser`, see [`docs/diagrams/README.md`](diagrams/README.md)
to regenerate them).

## What runs

| Service | Role | Default port |
|---|---|---|
| `llama-server` (CUDA, local process) | Serves **Qwen3.6-35B-A3B-MTP** | `8080` |
| Understory (Docker) | MCP memory layer | `3800` |
| Pithagoras (Docker) | Task portal | `4100` |

`llama-server` runs as a local process (not Docker) because it needs
direct GPU access. The rest are independent `docker compose` stacks.

`llama-server` binds to `127.0.0.1` only. Understory and Pithagoras bind
to `0.0.0.0` (required by `network_mode: host` in their compose files), so
without `ufw` they'd be reachable from the whole LAN. `ufw` is what
actually restricts those ports (`sudo ufw status verbose`); remote access
(another network, phone) goes through Tailscale instead of exposing the
port to the internet. If Tailscale connects but the port doesn't respond
while on the same wifi, see [`03-troubleshooting.md`](03-troubleshooting.md).

Voice (STT+TTS) is a self-contained Pithagoras add-on (`pithagoras-voice`,
see `docs/guide/voice.md` in that repo), toggled from its own
Settings → Add-ons.

## Lifecycle (async phases)

The whole boot/shutdown flow is handled through explicit `async` phases —
`rinthel_tui/lifecycle/`. The TUI starts at `SplashScreen` (duotone banner
composing itself out of noise, glitch reveal) → `MenuScreen`:

```
[0] INSTALL     -- Initial setup (CUDA/model/Pithagoras/Understory)
[1] BOOT        -- Bring everything up
[2] RELOAD      -- Full shutdown + restart
[3] TERMINATE   -- Full shutdown
[4] LOGS        -- Watch llama-server live
[5] CAPTURE     -- Capture MoE profile (routing profile)
[6] MONITOR     -- Services/Docker/GPU/CPU status
[7] CONFIGURE   -- Active services and parameters
[8] EXIT        -- Close terminal
```

```
SplashScreen (glitch reveal)
       │
       ▼
   MenuScreen
       │
       ├── [0] INSTALL   ──▶ 6 phases: preflight → build → pithagoras → understory
       ├── [1] BOOT       ──▶ docker → llama-server → understory → pithagoras
       ├── [2] RELOAD     ──▶ 9 phases: full shutdown → full boot
       └── [3] TERMINATE  ──▶ full shutdown
```

## Project structure

```
rinthel_tui/
├── app.py               # entry point — RinthelApp
├── config.py             # RinthelConfig — defaults + .env loading
├── branding/              # duotone ASCII banner + composition animation
├── theme/
│   ├── palette.py          # canonical palette — single source of truth
│   └── cyberpunk_theme.py
├── tui/
│   ├── screens/            # Splash, Menu, PhaseRunner, Logs, Monitor, Capture, Reload, Farewell
│   ├── widgets/             # sparkline, service_badge, checklist
│   └── effects/             # flicker, transitions, intro
└── lifecycle/
    ├── install.py           # [0] INSTALL phases
    ├── phases.py            # BOOT/DOWN/RELOAD phases
    ├── services.py            # argv builders + LocalProcessService/DockerComposeService per service
    ├── specs.py              # declarative phase lists
    ├── runner.py             # async runner with per-phase progress
    └── capture_profile.py    # MoE routing profile capture
```

## Ecosystem — shared palette

The duotone palette (`theme/palette.py`) isn't just this repo's:
Pithagoras' web frontend (`web/src/index.css`) implements it as
`[data-theme="cyberpunk"]` with the same hex values. Changing a color here
without updating the other side desyncs them visually.

| Role | Hex |
|-----|-----|
| Electric purple (frame, text) | `#BF00FF` |
| Neon yellow (lit face) | `#FCEE0A` |
| Electric cyan | `#7CFCFF` |
| Neon magenta | `#EA00D9` |
| Night city purple-black (background) | `#0D0221` |

## Development

`scripts/test_phases.py` runs individual phases or full lists against
real infrastructure, without going through Textual — useful for testing
`lifecycle/` changes quickly:

```bash
.venv/bin/python scripts/test_phases.py list
.venv/bin/python scripts/test_phases.py boot
.venv/bin/python scripts/test_phases.py spawn_llama
.venv/bin/python scripts/test_phases.py wait_port_free --port 8080
```

It's not a `pytest` test suite (it operates against real Docker/GPU, no
mocks) — that's intentional, it lives in `scripts/`, not `tests/`.
