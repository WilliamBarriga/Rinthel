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

[![Rust](https://img.shields.io/badge/client-ratatui-DEA584?style=flat-square)](https://github.com/ratatui-org/ratatui)
[![Python 3.13+](https://img.shields.io/badge/daemon-python_3.13+-BF00FF?style=flat-square)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-7CFCFF?style=flat-square)](LICENSE)

</div>

A local Instance of Rinthel: a Python/FastAPI daemon with a Rust/Ratatui TUI
(`rinthel/`) that runs the lifecycle of a CUDA `llama-server` serving the
active Local model, **Deck** (`deck/`, the web portal: login, Sessions, chat)
and **Understory** (`understory/`, MCP memory layer) in Docker.

## Quick install

**Ubuntu 26.04** — system dependencies and CUDA first, see
[`docs/06-ubuntu-installation.md`](docs/06-ubuntu-installation.md):

```bash
rinthel/install.sh            # venv, daemon, Rust client, opens the TUI
```

**Windows 11** — read [`docs/04-windows-installation.md`](docs/04-windows-installation.md) first:

```powershell
.\rinthel\install.ps1
```

Then, in the TUI: **INSTALL** (llama.cpp build, default Local model ~22 GB,
secrets and container user in the root `.env`, `rinthel.db` and the first
admin, whose password is shown once) and **BOOT**. Deck answers on
`http://127.0.0.1:4100`. `rinthel/rinthel-boot.sh` reopens the TUI;
`--stop` stops the daemon. Local voice (Linux only) is opt-in and
repeatable: `rinthel/install.sh --voice` brings the daemon up and runs INSTALL
with the voice ([docs/local-models.md](docs/local-models.md#voice)); then each
user turns it on for their own Sessions in Deck's Voz screen
([docs/deck/configuration.md](docs/deck/configuration.md#voice)).

## Hardware requirements

- NVIDIA GPU with at least **8 GB of VRAM**, CUDA toolkit, CMake.
- At least **32 GB of RAM**.
- Docker with `docker compose`.

## Documentation

- [`docs/01-system-overview.md`](docs/01-system-overview.md) — what runs, lifecycle phases, code structure.
- [`docs/02-hardware-optimization.md`](docs/02-hardware-optimization.md) — Linux inference profile.
- [`docs/03-troubleshooting.md`](docs/03-troubleshooting.md) — common errors.
- [`docs/04-windows-installation.md`](docs/04-windows-installation.md) and [`docs/05-windows-validation.md`](docs/05-windows-validation.md) — Windows bootstrap and its Validated profile.
- [`docs/06-ubuntu-installation.md`](docs/06-ubuntu-installation.md) — Ubuntu bootstrap.
- [`docs/07-host-exec.md`](docs/07-host-exec.md) — `hostexecd`.
- [`docs/local-models.md`](docs/local-models.md) — the Local model catalog, switching and routing.
- [`docs/deck/`](docs/deck/) — Deck architecture and configuration.
- [`docs/diagrams/`](docs/diagrams/) — architecture map.

Configuration lives in a single root `.env` (copy from `.env.example`).

## Credits

- **Understory** (MCP memory layer) by [thecodacus](https://github.com/thecodacus/understory).
- **`llama.cpp`** upstream ([`ggml-org/llama.cpp`](https://github.com/ggml-org/llama.cpp)), cloned and built with CUDA by INSTALL.

## License

MIT — see [`LICENSE`](LICENSE).

---

<div align="center">

*≖ω≖ — Rinthel, Night City 2077 | 道は目的地に在らず*

</div>
