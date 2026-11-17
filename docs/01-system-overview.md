# System Overview

What runs in an Instance, how it boots, and how the code is organized. For
the *why* behind `llama-server`'s inference flags, see
[`02-hardware-optimization.md`](02-hardware-optimization.md). For common
errors, see [`03-troubleshooting.md`](03-troubleshooting.md). The
architecture map is in [`docs/diagrams/`](diagrams/README.md) (`.dg` files,
opened with `scripts/diagrams.sh dev`).

## What runs

| Service | Role | Default port |
|---|---|---|
| `rinthel_tui.daemon` (local process) | Lifecycle, identity, Local models, Monitor | `8765` (loopback) |
| `llama-server` (CUDA, local process) | Serves the active Local model | `8080` |
| Deck (Docker, host network on Linux) | Web portal: login, Sessions, chat | `4100` |
| Understory (Docker) | MCP memory layer | `3800` |
| `hostexecd` (local process, Linux only) | Runs shell commands on the host for an admin's Session | `8766` (loopback) |

`llama-server` and the daemon run as local processes (GPU access, host
lifecycle); the daemon starts and stops `llama-server` and `hostexecd` as its
managed services (see [`07-host-exec.md`](07-host-exec.md)). Deck and Understory are services of the single root compose
project (`docker-compose.yaml`, `name: rinthel-general`): Deck enters by
`include: deck/docker-compose.yml`, Understory by `extends:`. There is one
`.env`, at the root.

Deck runs as `PUID:PGID` (written by INSTALL from the host user) so what it
writes under `data/deck` stays editable from the host. On Linux it shares the
host network and binds `4100` directly; on Windows the port is published on
loopback only (see [`04-windows-installation.md`](04-windows-installation.md)).

`llama-server` and Understory (published `3800:3800`) bind to `0.0.0.0`.
`ufw` restricts the host-process ports (`sudo ufw status verbose`). `3800`
is **not** covered by `ufw`: Docker-published ports are DNAT'ed and go
through `FORWARD`, not `INPUT`, so only `AUTH_TOKEN` protects it. Remote
access goes through Tailscale instead of exposing ports to the internet; if
Tailscale connects but a port does not answer on the same wifi, see
[`03-troubleshooting.md`](03-troubleshooting.md).

### Understory → llama-server

Understory calls the LLM for `memory_query` (and dreaming). Its container
sits on its own bridge and reaches the host like this:

| Piece | Value | Defined in |
|---|---|---|
| Bridge / subnet | `br-rgunderstory`, `172.30.99.0/24`, gateway `172.30.99.1` | `docker-compose.yaml` |
| Host alias | `host.docker.internal` → `172.30.99.1` (`extra_hosts: !override`) | `docker-compose.yaml` |
| LLM endpoint | `http://host.docker.internal:8080/v1` | root `.env` (`LLM_API_BASE_URL`) |
| llama-server bind | `0.0.0.0:8080` | `rinthel/rinthel_tui/lifecycle/services.py` |
| Firewall | `sudo ufw allow in on br-rgunderstory to any port 8080 proto tcp` | host (not in repo) |

The ufw rule is the **only** host-side piece. There must be **no NAT**:
recreating the bridge (`compose down && up`) resets a per-interface
`route_localnet=1` while a DNAT matched by interface name survives, so the
kernel silently drops every SYN as a martian — see
[`03-troubleshooting.md`](03-troubleshooting.md). Renaming the bridge or
changing the subnet requires updating the ufw rule in the same change; keep
the names distinct from any other environment on the same host.

Quick check from the host:

```bash
docker exec rinthel-general-understory-1 nc -zv -w3 host.docker.internal 8080
```

Its token: INSTALL writes one value as both `AUTH_TOKEN` (what Understory
requires) and `UNDERSTORY_TOKEN` (what a caller presents) in the root `.env`.
The live bundle is `data/understory`.

## Lifecycle

`rinthel/rinthel-boot.sh` (or `.ps1`) ensures the service secret in the root
`.env`, autostarts the daemon (pidfile, it survives the TUI closing) and
launches the Rust client, which
drives everything over the daemon's HTTP/WS API — see
[`adr/0001-daemon-protocol-shape.md`](adr/0001-daemon-protocol-shape.md).
Every route has an access policy (`public`, `service`, `service_as_user`,
`user`, `admin`; [`adr/0003-policy-de-acceso-por-ruta.md`](adr/0003-policy-de-acceso-por-ruta.md)).
The TUI sends `X-Rinthel-Service-Secret`; Deck users carry a Panel token.

```
MONITOR     -- Local models per Capability, managed services, Docker/GPU/CPU (live via /ws/monitor)
BOOT        -- Bring everything up               (POST /boot)
RELOAD      -- Full shutdown + restart            (POST /reload)
TERMINATE   -- Full shutdown                      (POST /terminate)
CONFIGURAR  -- Active services, parameters, secret rotation (GET/POST /config, POST /secrets/rotate)
LOGS        -- Watch llama-server live
INSTALL     -- Initial setup (POST /install)
SALIR       -- exit prompt ("¿apagar también el daemon?") → farewell
```

```
Rinthel Client (Ratatui)
       │  HTTP+WS 127.0.0.1:8765
       ▼
Rinthel Daemon (FastAPI, persistent)
       │
       ├── INSTALL    ──▶ preflight → llama.cpp + Local model → Instance (.env secrets,
       │                  host-exec token, PUID/PGID/DOCKER_GID) → identity (rinthel.db,
       │                  first admin) → Deck (Instance SOUL) → Understory (token, bundle)
       ├── BOOT       ──▶ docker → llama-server → hostexecd (Linux) → understory → deck
       ├── RELOAD     ──▶ 3 batches (phase_batch over WS): shutdown → boot → rebuild
       └── TERMINATE  ──▶ full shutdown (keeps going if a unit fails)
```

INSTALL configures, it never boots, and every phase is idempotent: a rerun
never replaces a secret or a file that is already there. The first admin's
password is shown once; `python -m rinthel_tui.identity reset-admin` is the
recovery. After BOOT, log in to Deck on `http://127.0.0.1:4100` with it.

## Project structure

```
docker-compose.yaml          # root compose: include deck/, extends understory/
.env.example                 # the single .env, documented
data/                        # state (git-ignored): rinthel.db, instance.toml, deck/, understory/
logs/                        # daemon, hostexecd and llama-server logs (git-ignored)
rinthel/
├── install.sh / install.ps1 / rinthel-boot.sh / rinthel-boot.ps1
├── rinthel_tui/             # daemon (FastAPI), headless
│   ├── daemon.py             # entry point
│   ├── api/                  # one package per area: config, ws, lifecycle, secrets, identity, models
│   │   ├── __init__.py        # create_app: the ordered list of areas
│   │   ├── adapters.py        # the only place that picks real adapters
│   │   └── access.py          # access policy per route
│   ├── config.py             # RinthelConfig: defaults per Platform + root .env
│   ├── instance.py           # Instance layout and secrets (also a CLI for the boot scripts)
│   ├── database.py           # rinthel.db migrations
│   ├── identity/             # users, Panel tokens, reset-admin
│   ├── models/               # Local model catalog, active model, switch
│   ├── monitoring/           # telemetry streams of /ws/monitor
│   ├── lifecycle/            # Host ports and adapters, plans, INSTALL phases, managed services
│   └── theme/palette.py      # canonical palette
├── hostexecd/               # host command daemon
├── rinthel-client/          # TUI (Ratatui), the only native UI
└── tests/
deck/                        # web portal: server (Node/Express, pi SDK), web (React), shared
understory/                  # MCP memory layer
docs/
```

## Tests

`cd rinthel && .venv/bin/python -m pytest -q` (daemon, INSTALL phases on a
fake `Host`, protocol fixtures shared with the Rust client);
`cd rinthel/rinthel-client && cargo test --locked`; `cd deck && npm test` and
`npm run test:browser` (Playwright over a fake daemon). The live checks are
in [`testing/live-checklist.md`](testing/live-checklist.md).
