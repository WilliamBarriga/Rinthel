# System Overview

What's running, how it boots, and how the code is organized. For the
*why* behind `llama-server`'s inference flags, see
[`02-hardware-optimization.md`](02-hardware-optimization.md). For common
errors, see [`03-troubleshooting.md`](03-troubleshooting.md).

See also: [monorepo structure diagram](diagrams/out/rinthel-monorepo-structure.html),
[runtime architecture diagram](diagrams/out/rinthel-runtime.html),
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
`rinthel_tui/lifecycle/` — but they no longer run in-process with the UI.
`./rinthel-boot.sh` autostarts the daemon (pidfile-tracked, survives the TUI
closing) if it isn't already up, then launches the Rust client. The client
opens straight on the menu (glitch-reveal title, no separate splash screen)
and drives everything through the daemon's HTTP/WS API — see
[`docs/adr/0001-daemon-protocol-shape.md`](adr/0001-daemon-protocol-shape.md).

```
MONITOR     -- Services/Docker/GPU/CPU status (live via /ws/monitor)
BOOT        -- Bring everything up               (POST /boot)
RELOAD      -- Full shutdown + restart            (POST /reload)
TERMINATE   -- Full shutdown                      (POST /terminate)
CONFIGURAR  -- Active services and parameters     (GET/POST /config)
CAPTURE     -- Capture MoE profile (simulated)     (POST /capture)
LOGS        -- Watch llama-server live
INSTALL     -- Initial setup (CUDA/model/Pithagoras/Understory) (POST /install)
SALIR       -- exit prompt ("¿apagar también el daemon?") → farewell
```

```
Rinthel Client (Ratatui)
       │  HTTP+WS 127.0.0.1:8765
       ▼
Rinthel Daemon (FastAPI, persistent — pidfile, survives client exit)
       │
       ├── INSTALL    ──▶ 6 phases: preflight → build → pithagoras → understory
       ├── BOOT        ──▶ docker → llama-server → understory → pithagoras
       ├── RELOAD      ──▶ 3 tandas (con phase_batch por WS): shutdown → boot → rebuild
       └── TERMINATE   ──▶ full shutdown (sigue con lo que queda si una unidad falla)
```

## Project structure

This is a monorepo: two native processes (daemon + client) plus Understory
and Pithagoras vendored in as `git subtree`s, each still pushable back to
its own personal fork — see [Repos](../README.md#repos) in the README and
the [monorepo structure diagram](diagrams/out/rinthel-monorepo-structure.html)
for the fork/upstream relationships. A single root `docker-compose.yaml`
(`include:`) brings up both subtrees' stacks; the Python side is daemon-only
— no more `app.py`/Textual `tui/` (deleted, parity reached, see git history
if you need it); all screens live in the Rust client.

```
docker-compose.yaml           # root — include: understory/ + pithagoras/
understory/                  # git subtree (WilliamBarriga/understory fork)
pithagoras/                  # git subtree (WilliamBarriga/pithagoras fork)
rinthel_tui/                 # daemon (FastAPI) — headless, no UI code
├── daemon.py                 # entry point — routes, cfg owner, /ws/monitor
├── phase_bridge.py            # PhaseReport -> ServiceOutcome + phase_status/phase_log
├── config_routes.py           # GET/POST /config shape + validate-before-write
├── config.py                  # RinthelConfig — defaults + .env loading
├── env_file.py                 # writes .env overrides
├── theme/
│   └── palette.py               # canonical palette — single source of truth
├── monitoring/
│   ├── resources.py              # GPU/CPU/RAM sampling
│   └── services.py                # docker compose ps
└── lifecycle/
    ├── install.py                 # INSTALL phases
    ├── phases.py                   # BOOT/DOWN/RELOAD phases
    ├── managed_service.py           # LocalProcessService/DockerComposeService
    ├── services.py                   # argv builders per service
    ├── specs.py                       # declarative phase lists
    ├── runner.py                       # async runner with per-phase progress
    └── capture_profile.py               # MoE routing profile capture (POST /capture is simulated)

rinthel-client/               # TUI (Ratatui) — the only UI, talks HTTP+WS to the daemon
├── src/
│   ├── main.rs                 # entry point
│   ├── app.rs                    # event loop, daemon base URL, effect state
│   ├── protocol.rs                 # serde structs mirroring the daemon's JSON
│   ├── screens/                     # menu, monitor, logs, capture, phase_runner,
│   │                                  settings, exit_prompt, farewell
│   ├── widgets/                      # checklist, log_tail
│   └── effects/                       # flicker (glitch reveal), tagline, transitions
└── tests/                     # e2e_smoke.rs, protocol_fixtures.rs
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
real infrastructure, without going through the daemon or the client —
useful for testing `lifecycle/` changes quickly:

```bash
.venv/bin/python scripts/test_phases.py list
.venv/bin/python scripts/test_phases.py boot
.venv/bin/python scripts/test_phases.py spawn_llama
.venv/bin/python scripts/test_phases.py wait_port_free --port 8080
```

It's not a `pytest` test suite (it operates against real Docker/GPU, no
mocks) — that's intentional, it lives in `scripts/`, not `tests/`. It talks
to `lifecycle/` directly, bypassing both the daemon's HTTP layer and the
Rust client.

For the client/daemon pair itself: `rinthel-client/tests/e2e_smoke.rs` (real
daemon subprocess) and `protocol_fixtures.rs` (JSON shape checks) on the
Rust side; `tests/daemon/` on the Python side.
