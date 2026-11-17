# Rinthel Ratatui client

The admin's terminal UI: the menu (MONITOR, BOOT, RELOAD, TERMINATE,
CONFIGURAR, LOGS, INSTALL, SALIR), the live Monitor, the progress of each
lifecycle command, the logs and the configuration. It holds no business
logic: it asks the daemon for everything over REST and reads the
`/ws/monitor` tunnel ([ADR 0001](../../docs/adr/0001-daemon-protocol-shape.md)).

## Running it

**Normal use:** `./rinthel-boot.sh` from `rinthel/` (`rinthel-boot.ps1` on
Windows). It rebuilds the client if it changed, starts the daemon if it is
not listening and opens the binary (`target/release/rinthel`) with the port
and the service secret from the Instance's `.env`. `./rinthel-boot.sh --stop`
stops the daemon.

**Debugging** (without `rinthel-boot.sh`):

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
service Caller ([ADR 0003](../../docs/adr/0003-policy-de-acceso-por-ruta.md)).
Rotating `RINTHEL_SERVICE_SECRET` from CONFIGURAR hands the new secret back to
the client, which adopts it without rereading the `.env`.

## How it is built

- **Hand-written protocol:** `src/protocol.rs` mirrors the daemon's JSON with
  `serde` structs, no codegen. Both sides read the same golden JSON files
  (`rinthel/tests/protocol_fixtures/`): `tests/protocol_fixtures.rs` here,
  `tests/protocol/test_fixtures.py` and
  `tests/daemon/test_protocol_fixtures_http.py` in the daemon.
- **The daemon decides what is shown:** the Monitor paints one line per
  Capability and one badge per managed service exactly as `models_status`
  reports them (the daemon leaves out what the Instance does not run on its
  Platform); the client only groups and orders. CONFIGURAR marks a
  hardware/cache field whose value differs from the Validated profile.
- **Unknown tags are ignored:** a tunnel message with a tag the client does
  not know is dropped without error.
- **Reconnect without replay:** if the daemon goes down the client stays alive
  and reconnects; the next message brings fresh state.
- **Theme:** the daemon serves the palette (`GET /theme`); `ratatui-sci-fi`
  brings the Cyberpunk theme and the `EnergyGauge`.

## Tests

```bash
cargo test --locked
```

`tests/protocol_fixtures.rs` reads the same golden JSON files as the daemon's
tests; the tests in `src/` draw each screen on a `TestBackend` and talk to a
fake HTTP server on loopback. None of them starts the daemon or the Instance.
