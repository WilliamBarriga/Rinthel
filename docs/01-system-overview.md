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

`llama-server`, Pithagoras and Understory (published `3800:3800`) all
bind to `0.0.0.0`. Without `ufw`, `8080` and `4100` would be reachable
from the whole LAN. `3800` is **not** covered by `ufw`: Docker-published
ports are DNAT'ed and go through `FORWARD`, not `INPUT`, so ufw rules
never see them — only `AUTH_TOKEN` protects it. `ufw` is what restricts
the host-process ports
(`sudo ufw status verbose`); remote access (another network, phone) goes
through Tailscale instead of exposing the port to the internet. If
Tailscale connects but the port doesn't respond while on the same wifi,
see [`03-troubleshooting.md`](03-troubleshooting.md).

### Understory → llama-server

Understory calls the LLM for `memory_query` (and dreaming). Its container
sits on its own bridge and reaches the host like this:

| Piece | Value | Defined in |
|---|---|---|
| Bridge / subnet | `br-rgunderstory`, `172.30.99.0/24`, gateway `172.30.99.1` | `docker-compose.yaml` |
| Host alias | `host.docker.internal` → `172.30.99.1` (`extra_hosts: !override`) | `docker-compose.yaml` |
| LLM endpoint | `http://host.docker.internal:8080/v1` | `understory/docker-compose.yml` |
| llama-server bind | `0.0.0.0:8080` | `rinthel_tui/lifecycle/services.py` |
| Firewall | `sudo ufw allow in on br-rgunderstory to any port 8080 proto tcp` | host (not in repo) |

The ufw rule is the **only** host-side piece. There must be **no NAT**:
an old `understory-llama-nat.service` DNAT'ed `8080` to `127.0.0.1`
with a per-interface `route_localnet=1`. Recreating the bridge
(`compose down && up`) resets that sysctl while the DNAT (matched by
interface name) survives, so the kernel silently drops every SYN as a
martian — see [`03-troubleshooting.md`](03-troubleshooting.md).

Renaming the bridge or changing the subnet requires updating the ufw rule
in the same change. Rinthel-corp uses `br-rcunderstory` /
`172.31.99.0/24` on the same host; keep the names distinct.

Quick check from the host:

```bash
docker exec rinthel-general-understory-1 nc -zv -w3 host.docker.internal 8080
```

Voice (STT+TTS) is a self-contained Pithagoras add-on (`pithagoras-voice`,
see `docs/guide/voice.md` in that repo), toggled from its own
Settings → Add-ons.

## Lifecycle (async phases)

The whole boot/shutdown flow is handled through explicit `async` phases —
`rinthel_tui/lifecycle/` — but they no longer run in-process with the UI.
`rinthel/rinthel-boot.sh` autostarts the daemon (pidfile-tracked, survives the TUI
closing) if it isn't already up, then launches the Rust client. The client
opens straight on the menu (glitch-reveal title, no separate splash screen)
and drives everything through the daemon's HTTP/WS API — see
[`docs/adr/0001-daemon-protocol-shape.md`](adr/0001-daemon-protocol-shape.md).
Every route the client calls requires the service secret
(`X-Rinthel-Service-Secret`, or `?token=` on the `/ws/monitor` handshake):
`rinthel-boot.sh`/`.ps1` generate `RINTHEL_SERVICE_SECRET` in the root `.env`
if it is missing and export it to the client. Without it the daemon answers
401 (the WebSocket closes with 4401).

```
MONITOR     -- Local models per Capability, managed services, Docker/GPU/CPU (live via /ws/monitor)
BOOT        -- Bring everything up               (POST /boot)
RELOAD      -- Full shutdown + restart            (POST /reload)
TERMINATE   -- Full shutdown                      (POST /terminate)
CONFIGURAR  -- Active services, parameters, secret rotation (GET/POST /config, POST /secrets/rotate)
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
       ├── INSTALL    ──▶ preflight → llama.cpp + model → instance secrets → pithagoras → understory
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
├── daemon.py                 # entry point — builds the app and serves it
├── api/                      # HTTP layer, one package per area (config, ws, lifecycle, secrets)
│   ├── __init__.py            # create_app: the ordered list of areas
│   ├── adapters.py            # the only place that picks real adapters
│   └── access.py              # access policy per route (public, service)
├── config.py                  # RinthelConfig — defaults + .env of the Instance
├── config_edits.py            # GET/POST /config shape + validate-before-write, secret rotation
├── instance.py                # Instance layout and secrets (also a CLI for the boot scripts)
├── env_file.py                 # writes .env overrides
├── theme/
│   └── palette.py               # canonical palette — single source of truth
├── monitoring/                # Telemetry streams of /ws/monitor
│   ├── domain/                  # Monitor, envelope, one port per source
│   └── adapters/                # nvidia-smi, psutil, docker compose ps, log tail, HTTP readiness, in-memory
└── lifecycle/
    ├── domain/                  # Host (8 ports), types, phases (managed service, docker, data dir)
    ├── adapters/                # real adapter per Host port
    ├── composition.py           # real_host(): picks the adapters
    ├── install.py / install_tasks.py  # INSTALL phases and their tasks
    ├── managed_service.py       # LocalProcessService/DockerComposeService definitions
    ├── services.py              # argv builders per service
    ├── specs.py                 # Lifecycle plans (batches, units, failure policy)
    ├── executor.py              # runs a plan, broadcasts phase_status/phase_log/phase_batch
    └── commands.py              # Lifecycle: boot/terminate/reload/install

rinthel-client/               # TUI (Ratatui) — the only UI, talks HTTP+WS to the daemon
├── src/
│   ├── main.rs                 # entry point
│   ├── app.rs                    # event loop, daemon base URL, effect state
│   ├── protocol.rs                 # serde structs mirroring the daemon's JSON
│   ├── screens/                     # menu, monitor, logs, phase_runner,
│   │                                  settings, exit_prompt, farewell
│   ├── widgets/                      # checklist, log_tail
│   └── effects/                       # flicker (glitch reveal), tagline, transitions
└── tests/                     # protocol_fixtures.rs
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

For the client/daemon pair itself: `rinthel-client/tests/protocol_fixtures.rs`
and the screen tests in `rinthel-client/src/` on the Rust side;
`tests/daemon/` (including `test_protocol_fixtures_http.py`, over the same
golden JSON files) on the Python side.
