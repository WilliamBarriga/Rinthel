# rinthel: the daemon and its terminal client

The control plane of a Rinthel Instance. The **daemon** (Python/FastAPI,
`rinthel_tui/`) runs the lifecycle of the managed services (the
`llama-server` of the active Local model, Understory and Deck in Docker,
`hostexecd` and, opt-in, the voice services on Linux), owns identity
(`data/rinthel.db`) and the Local model catalog, and hands Deck the routes to
the local models. The **client** (Rust/Ratatui, `rinthel-client/`) is the
admin's terminal UI; it talks to the daemon over REST plus the `/ws/monitor`
WebSocket ([ADR 0001](../docs/adr/0001-daemon-protocol-shape.md)).
`hostexecd/` is the small host process the daemon runs for Deck's host exec
tools ([`docs/07-host-exec.md`](../docs/07-host-exec.md)).

The vocabulary is in [`GLOSSARY.md`](GLOSSARY.md); the docs of the whole
Instance are indexed in the [root README](../README.md).

## Install

```bash
rinthel/install.sh                 # bootstrap and open the TUI
rinthel/install.sh --skip-launch   # bootstrap only
rinthel/install.sh --voice         # bootstrap, then INSTALL with local voice (Linux only)
```

`install.sh` (`install.ps1` on Windows) finds Python 3.13+, creates
`rinthel/.venv`, installs the daemon, installs Rust with `rustup` if `cargo` is
missing and builds the client. It touches neither the GPU, CUDA nor Docker:
that is **INSTALL** in the TUI (the `INSTALL_UNITS` of
`rinthel_tui/lifecycle/install.py`): llama.cpp built with CUDA and the
default Local model, the Instance secrets in the root `.env`, `rinthel.db`
and the first admin (its password is shown once), Deck and Understory. Each
phase is idempotent and skips what exists; INSTALL configures, it does not
boot. Platform guides: [Ubuntu](../docs/06-ubuntu-installation.md),
[Windows](../docs/04-windows-installation.md).

Lost the admin password? On the host:
`rinthel/.venv/bin/python -m rinthel_tui.identity reset-admin [--username admin]`
prints a new one once (local access only, no HTTP).

By hand instead of `install.sh`:

```bash
python3 -m venv rinthel/.venv && rinthel/.venv/bin/pip install -e rinthel
(cd rinthel/rinthel-client && cargo build --release --locked)
```

## Usage

```bash
rinthel/rinthel-boot.sh                # starts the daemon if needed, opens the client
rinthel/rinthel-boot.sh --stop         # stops the daemon without opening the client
rinthel/rinthel-boot.sh --daemon-only  # starts the daemon, no client
```

`rinthel-boot.sh` (`rinthel-boot.ps1` on Windows) generates
`RINTHEL_SERVICE_SECRET` if the `.env` lacks it, rebuilds the client if it
changed, starts the daemon if nothing listens on its port (pidfile at the
Instance root, log in `logs/daemon.log`; it outlives the client) and opens the
client with the port and the service secret. The menu:

```
MONITOR     -- each Capability's Local model and each managed service, live
BOOT        -- bring the Instance up
RELOAD      -- full shutdown + boot + rebuild
TERMINATE   -- full shutdown
CONFIGURAR  -- the .env parameters, marking overrides of the Validated profile
LOGS        -- follow llama-server's log
INSTALL     -- initial setup
SALIR       -- exit (asks whether to also stop the daemon)
```

The Local model is switched offline with `python -m rinthel_tui.models
list|use <id>|off stt|tts` (services stopped), or live by an admin from Deck
([`docs/local-models.md`](../docs/local-models.md)).

## Configuration

Infra settings (paths, ports, inference flags) have a default in
`rinthel_tui/config.py`, overridden by the Instance's root `.env` (resolved
by `rinthel_tui/instance.py`); a `RINTHEL_*` exported in the shell wins over
both. Start from the root `.env.example`. The hardware values of each
Platform's Validated profile live once in `VALIDATED_PROFILES`
([`docs/02-hardware-optimization.md`](../docs/02-hardware-optimization.md)).
The active Local model per Capability is not in `.env`: it is
`data/instance.toml`, over the hand-edited catalog `models.local.json`.

A `*_BIN` or model path that does not exist does not stop the daemon: it warns
in its log and the failure shows when that service starts
([`docs/03-troubleshooting.md`](../docs/03-troubleshooting.md)).

## The client

It holds no business logic: everything comes from the daemon.

**Debugging without `rinthel-boot.sh`:**

1. The daemon by hand, which keeps the terminal busy:
   ```bash
   cd rinthel && .venv/bin/python -m rinthel_tui.daemon
   ```
2. In another terminal, the client against that daemon, with the same secret:
   ```bash
   cd rinthel/rinthel-client
   RINTHEL_SERVICE_SECRET="$(../.venv/bin/python -m rinthel_tui.instance get RINTHEL_SERVICE_SECRET)" cargo run
   ```
   `cargo run -- --port N` if the daemon is not on `8765`.

Without the secret the daemon answers 401 to everything: the client is a
service Caller ([ADR 0003](../docs/adr/0003-policy-de-acceso-por-ruta.md)).
Rotating `RINTHEL_SERVICE_SECRET` from CONFIGURAR hands the new secret back to
the client, which adopts it without rereading the `.env`.

- **Hand-written protocol:** `rinthel-client/src/protocol.rs` mirrors the
  daemon's JSON with `serde` structs, no codegen. Both sides read the same
  golden JSON files (`tests/protocol_fixtures/`):
  `rinthel-client/tests/protocol_fixtures.rs` there,
  `tests/protocol/test_fixtures.py` and
  `tests/daemon/test_protocol_fixtures_http.py` in the daemon.
- **The daemon decides what is shown:** the Monitor paints one line per
  Capability and one badge per managed service exactly as `models_status`
  reports them, and CONFIGURAR lists what `GET /config` returns; the daemon
  leaves out what the Instance does not run on its Platform. The client only
  groups and orders.
- **Unknown tags are ignored:** a tunnel message with a tag the client does
  not know is dropped without error.
- **Reconnect without replay:** if the daemon goes down the client stays alive
  and reconnects; the next message brings fresh state.
- **Theme:** the daemon serves the palette (`GET /theme`); `ratatui-sci-fi`
  brings the Cyberpunk theme and the `EnergyGauge`.

## Tests

```bash
cd rinthel && .venv/bin/python -m pytest -q          # daemon (live tests are opt-in)
cd rinthel/rinthel-client && cargo test --locked     # client
```

The daemon's tests build every config on an Instance in `tmp_path` and run
the lifecycle over doubles of the `Host` ports; `tests/import_table.py` is the
table of allowed imports per module. The client's tests draw each screen on a
`TestBackend` and talk to a fake HTTP server on loopback. None of them starts
the daemon or touches the real Instance.
