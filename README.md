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

TUI (Rust/Ratatui client talking to a Python/FastAPI daemon over a local
WebSocket+REST protocol — see `.scratch/ratatui-migration/`) for managing
the lifecycle of Rinthel's local infrastructure: a
`llama-server` (CUDA) serving **Qwen3.6-35B-A3B-MTP** plus the Docker stacks
for **Understory** (MCP memory layer) and **Pithagoras** (task portal).

**Documentation:**

- [`docs/01-system-overview.md`](docs/01-system-overview.md) — what runs,
  lifecycle phases, code structure.
- [`docs/02-hardware-optimization.md`](docs/02-hardware-optimization.md) —
  why each inference flag is set the way it is (VRAM, quant, MoE cache).
- [`docs/03-troubleshooting.md`](docs/03-troubleshooting.md) — common errors
  and how to fix them.

## `[0]` Quick install (new machine)

One command, with no prior dependency beyond being able to install Python:

```bash
git clone <this-repo-url> && cd Rinthel-general && ./install.sh
```

`install.sh` detects (or installs, via the `deadsnakes` PPA if needed)
Python 3.13+, creates the venv, bootstraps Rust (`rustup`, non-interactive)
if `cargo` is missing, builds the client (`cargo build --release`), and
starts the TUI. From there, **`INSTALL`** in the menu runs 6 phases:

| Phase | What it does |
|------|----------|
| `1/6` PREFLIGHT | Detects GPU/CUDA/cmake/docker |
| `2/6` LLAMA.CPP | Clones the custom fork (`perf` branch) |
| `3/6` LLAMA.CPP | CUDA build, `native` architecture (not pinned) |
| `4/6` MODEL GGUF | Downloads the configured model |
| `5/6` PITHAGORAS | Clone + configuration |
| `6/6` UNDERSTORY | Scaffold + configuration |

Rules:

- `NVIDIA driver` + `CUDA toolkit` must already be installed — `INSTALL`
  detects them but doesn't install them.
- It's re-runnable: each phase is idempotent, skips what already exists.
- `INSTALL` configures, it doesn't boot — once it's done, use `BOOT` to
  bring everything up.

## Hardware requirements

- NVIDIA GPU with at least **8 GB of VRAM** (for `llama-server`'s CUDA
  offload; the rest of the model's layers run on CPU via `--n-cpu-moe`,
  adjustable in `.env`).
- At least **32 GB of RAM**.

## Requirements

- Python 3.13+ (daemon) + a Rust toolchain (client) — `install.sh`
  bootstraps both (`rustup`, non-interactive, if `cargo` is missing)
- A `llama.cpp` build with CUDA support (`llama-server`, and optionally
  `llama-moe-trace` for capturing MoE routing profiles)
- The GGUF model — default is **Qwen3.6-35B-A3B-MTP** at `Q4_K_XL`
  quantization (see `.env.example` for other models)
- Docker + `docker compose` if you're going to run Understory/Pithagoras
- `nvidia-container-toolkit` installed and configured (`nvidia-ctk runtime
  configure --runtime=docker`) if you're going to use Pithagoras' voice
  add-on (`pithagoras-voice` requires GPU via Docker) — without this,
  `docker info` won't detect the NVIDIA runtime and the add-on can't start
  (see `docs/guide/voice.md` in the Pithagoras repo)
- The Understory and Pithagoras repos cloned somewhere (configurable
  paths, see [Configuration](#configuration))

## Installation

`./install.sh` (see above) does the whole thing. To do it by hand:

**Daemon** (Python — dev mode, recommended if you're going to touch the code):

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

**Client** (Rust):

```bash
cd rinthel-client && cargo build --release
```

## Usage

From the repo root. Full lifecycle details (phases, diagram, services) in
[`docs/01-system-overview.md`](docs/01-system-overview.md):

```bash
./rinthel-boot.sh
```

`rinthel-boot.sh` resolves `.venv/bin/python` and `rinthel-client/target/release/rinthel`
relative to itself — **it must always be run from (or with cwd inside) the
repo root**; it's not meant to be symlinked or copied elsewhere. It
autostarts the daemon if it isn't already listening (pidfile at
`.rinthel-daemon.pid`, survives the client closing) and then launches the
Rust client, which opens straight into the menu (no splash screen):

```
MONITOR     -- Services/Docker/GPU/CPU status
BOOT        -- Bring everything up
RELOAD      -- Full shutdown + restart
TERMINATE   -- Full shutdown
CONFIGURAR  -- Active services and parameters
CAPTURE     -- Capture MoE profile (routing profile)
LOGS        -- Watch llama-server live
INSTALL     -- Initial setup (CUDA/model/Pithagoras/Understory)
SALIR       -- Exit (prompts whether to also stop the daemon)
```

To stop the daemon without opening the client: `./rinthel-boot.sh --stop`.

## Configuration

All of `llama-server`'s paths, ports and inference flags have an embedded
default in `rinthel_tui/config.py::default_config()`. To tune them for
your machine, copy `.env.example` to `.env` at the repo root and
uncomment/adjust what you need:

```bash
cp .env.example .env
```

`.env` loads automatically when `rinthel_tui.config` is imported (via
`python-dotenv`, searching upward from the cwd) and is never committed
(it's in `.gitignore`). Without a `.env`, the embedded defaults from
`rinthel_tui/config.py::default_config()` are used.

Available variables: binary/model/log paths, each service's port, and all
the inference flags (`-c`, `--temp`, `--top-p`, `--n-cpu-moe`, `--threads`,
etc.) — see `.env.example` for the full list with their values, and
[`docs/02-hardware-optimization.md`](docs/02-hardware-optimization.md) for
why each inference flag is set the way it is.

If `RINTHEL_LLAMA_BIN` or `RINTHEL_LLAMA_MODEL_PATH` point at something
that doesn't exist, the app **doesn't crash on startup** — it just warns
on stderr. The real failure (with a clear message) only happens if you
pick BOOT and the llama-server spawn phase actually fails. More cases in
[`docs/03-troubleshooting.md`](docs/03-troubleshooting.md).

## Credits

Three pieces of infrastructure that `[0] INSTALL` sets up are from
[thecodacus](https://github.com/thecodacus):

- **Understory** (MCP memory layer) — runs from the published image
  [`ghcr.io/thecodacus/understory`](https://github.com/thecodacus/understory),
  not cloned or built from source, see `phase_install_setup_understory` in
  `rinthel_tui/lifecycle/install.py`.
- **Pithagoras** (task portal) — the work is
  [thecodacus](https://github.com/thecodacus/pithagoras)'s; used via my
  fork [`WilliamBarriga/pithagoras`](https://github.com/WilliamBarriga/pithagoras).
- The custom **`llama.cpp`** fork (`perf` branch, default
  `RINTHEL_LLAMACPP_REPO_URL=https://github.com/thecodacus/llama.cpp.git`)
  that gets cloned and built with CUDA support.

## License

MIT — see [`LICENSE`](LICENSE).

---

<div align="center">

*≖ω≖ — Rinthel, Night City 2077 | 道は目的地に在らず*

</div>
