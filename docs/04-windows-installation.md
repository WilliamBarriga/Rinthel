# Installing on Windows 11

On Windows the client, the daemon and `llama-server` run as native processes.
Deck and Understory are Linux containers and need Docker Desktop. Voice and
host exec are Linux only: INSTALL and BOOT skip them on Windows.

## Requirements

1. Windows 11, up to date, with WSL 2 and the NVIDIA driver.
2. Python 3.13 or later, from the [official documentation](https://docs.python.org/3.13/using/windows.html).
3. Rust through [rustup](https://www.rust-lang.org/tools/install).
4. [CMake](https://cmake.org/download/) and Visual Studio Build Tools 2022 with
   the "Desktop development with C++" workload.
5. A [CUDA Toolkit](https://developer.nvidia.com/cuda-downloads) that matches the installed driver.
6. [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)
   with the WSL 2 backend and Linux containers. Host networking is not needed:
   Deck runs in a bridge network.

On a machine without WSL, open PowerShell as administrator, run
`wsl --install` and restart when Windows asks. This is a one-time change to
the operating system.

After installing tools, open a new PowerShell so the `PATH` changes are
visible.

## Bootstrap

From the repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\rinthel\install.ps1
```

The script is a thin wrapper: it creates the virtual environment in
`rinthel\.venv`, installs the daemon, builds `rinthel.exe`, writes the
machine paths (llama.cpp, models, logs under `%USERPROFILE%\Rinthel-data`) to
the root `.env` if it does not exist yet, and opens the TUI. It never
overwrites an existing `.env` and never writes the Validated profile: that
lives in the daemon config (see [`05-windows-validation.md`](05-windows-validation.md)).
Without explicit variables the daemon picks its Platform's defaults.

The root `.env.example` documents the Linux values. On Windows, let
`install.ps1` and INSTALL write the `.env`; do not copy the example over an
existing Windows `.env`.

In the TUI, run `INSTALL`. It checks CUDA and Docker, builds llama.cpp,
downloads the model (about 22 GB), generates the secrets of the root `.env`,
creates the first admin (its password is shown once), prepares Understory and
selects the Windows compose by writing to the root `.env`:

```text
COMPOSE_FILE=docker-compose.yaml;compose/windows.override.yaml
COMPOSE_PATH_SEPARATOR=;
```

A `COMPOSE_FILE` you already set is kept (INSTALL warns if it is not the one
above). INSTALL writes no `PUID`/`PGID`/`DOCKER_GID` and no host exec token on
Windows, and `--voice` is only a notice.

While it builds or downloads, open another PowerShell at the root and run:

```powershell
.\rinthel\install-status.ps1 -Watch
```

`INSTALL COMPLETO` means the server, the model, the secrets of the root
`.env`, the Understory bundle and the Windows `COMPOSE_FILE` are there. Close
the monitor with `Ctrl+C`; it does not stop the installation.

## Daily use

```powershell
.\rinthel\rinthel-boot.ps1
```

To stop only the persistent daemon:

```powershell
.\rinthel\rinthel-boot.ps1 -Stop
```

The daemon stays in the background when the TUI closes. On the next normal
use there is no need to repeat `INSTALL`: run `rinthel-boot.ps1` and use
`BOOT` only when a service is stopped.

## How Deck runs on Windows

`compose/windows.override.yaml` changes only what Windows needs:

- Deck runs in a bridge network instead of the host network, published on
  `http://127.0.0.1:4100` only (`RINTHEL_DECK_PORT`).
- Deck reaches the daemon and `llama-server` through `host.docker.internal`.
  The daemon builds every URL it hands Deck with `deck.host_address`, which
  defaults to `host.docker.internal` on Windows.
- Deck and Understory share a network: Deck reaches Understory at
  `http://understory:3800`. Understory is still published on `127.0.0.1:3800`
  only, and reaches the host through `host-gateway`.
- The Instance browser in docker mode: Deck creates `deck-browser` on a user
  network it shares with it (`rinthel-general_deck_browser`) and reaches its
  CDP (`9222`), view (`3011`) and stream (`8082`) by container name. Nothing
  of the browser is published on the host. A local Chrome or an external
  browser goes through `host.docker.internal` (set `BROWSER_CDP_URL` in the
  root `.env`).
- `deck.db` runs in `DELETE` journal mode (WAL needs shared memory the bind
  mount cannot give); Deck logs the mode at startup.
- Deck runs as the image's user: `PUID`, `PGID` and `DOCKER_GID` are Linux
  only. The Docker socket is still mounted for the browser's docker mode.
- No tailscale: remote access on Windows is out of scope.

Passwords and tokens stay in the root `.env` and must never be added to the
repository.

## Quick diagnosis

```powershell
python --version
cargo --version
cmake --version
nvcc --version
docker info
nvidia-smi
docker compose config --quiet
```

If `docker info` fails, open Docker Desktop and wait until it has started. If
`nvcc` is missing, check that the CUDA Toolkit added its `bin` folder to
`PATH`, or set `CUDA_PATH`. `docker compose config --quiet`, run at the root,
checks the root compose together with the override that `COMPOSE_FILE` names.

Use 64-bit PowerShell. The bootstrap refuses PowerShell `(x86)`, because the
binaries, paths and build tools it needs are 64-bit. If the execution policy
blocks the scripts, relax it for the current terminal only:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

If Deck does not answer, check that `llama-server`, Deck and Understory are
`ONLINE` in `MONITOR`, and that the root `.env` has the `COMPOSE_FILE` above;
`INSTALL` can be repeated without replacing secrets. What is still to be
checked on real Windows is listed in
[`05-windows-validation.md`](05-windows-validation.md#windows-checklist).
