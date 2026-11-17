# Installing on Ubuntu 26.04

Linux is the normal INSTALL: one root compose, data in `data/`, secrets
generated locally in the root `.env`. There is no separate Ubuntu profile and
no `COMPOSE_FILE`.

## 1. Ubuntu dependencies

In a normal terminal (do not run Rinthel as root):

```bash
sudo apt update
sudo apt install -y python3-venv build-essential curl ca-certificates git cmake pkg-config docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Log out and back in so the Docker group applies. Then:

```bash
docker info
docker compose version
```

The Docker group can manage containers with privileges over the host. INSTALL
writes its GID as `DOCKER_GID` in the root `.env`. Do not mix Ubuntu's
`docker.io` packages with Docker CE; if you prefer CE, follow only the
[official Docker guide](https://docs.docker.com/engine/install/ubuntu/).

Node/npm are not needed on the host. The installer uses rustup when Cargo is
missing. Ubuntu 26.04 already ships a compatible Python; do not add deadsnakes.

## 2. CUDA

`nvidia-smi`'s "CUDA 13.x" line is what the driver supports, not an installed
`nvcc`. Ubuntu's own `nvidia-cuda-toolkit` can be older than a recent GPU
(12.4 on the reference machine, older than its Blackwell RTX 5070): use
NVIDIA's repository for Ubuntu 26.04, which supports CUDA 13.4 with the R615
driver branch.

Sources: [CUDA Linux](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/),
[CUDA/driver versions](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/),
[driver for Ubuntu](https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/ubuntu.html).

```bash
curl -fL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2604/x86_64/cuda-keyring_1.1-1_all.deb -o /tmp/cuda-keyring_1.1-1_all.deb
sudo dpkg -i /tmp/cuda-keyring_1.1-1_all.deb
sudo apt update
sudo apt install linux-headers-$(uname -r)
sudo apt install nvidia-open cuda-toolkit-13-4
```

Review what APT proposes before accepting, especially if you already have
NVIDIA packages from another source. With Secure Boot on, complete the MOK
enrollment if the installer asks for it. Reboot when done.

In a new terminal:

```bash
export PATH=/usr/local/cuda-13.4/bin:$PATH
nvidia-smi
nvcc --version
```

Add that `export PATH=...` once at the end of `~/.bashrc` so it persists. Do
not go on to INSTALL while `nvidia-smi` or `nvcc` fail. Do not use
`--allow-unsupported-compiler` as an automatic fix.

## 3. Install Rinthel

From the repository root:

```bash
rinthel/install.sh --skip-launch
```

The script installs Rust if missing, creates `rinthel/.venv`, installs the
daemon and builds the client. It neither downloads the model nor starts the
containers. Do not reuse a `.venv` or absolute paths from Windows. `.env`,
`data/` and `models.local.json` are ignored by Git.

Deck uses the host network, so it reaches the daemon and the model on
`127.0.0.1:8080` (`deck.host_address`) without special iptables rules. The web
servers listen on the host's interfaces; limit access from other machines
with your firewall if you only want local use.

Check the configuration without printing secrets:

```bash
docker compose config --quiet
rinthel/rinthel-boot.sh
```

In the TUI:

1. **INSTALL**: checks dependencies, builds upstream llama.cpp (ggml-org,
   `master`) with CUDA, downloads the default Local model's GGUF (about
   22 GB) and writes the initial catalog `models.local.json` with that model
   active ([`local-models.md`](local-models.md)). It generates in the root
   `.env` the Instance secrets, the host exec token, `PUID`/`PGID` (your user,
   which Deck runs as), `DOCKER_GID`, and Understory's token
   (`UNDERSTORY_TOKEN`, the only source) with its bundle in `data/understory`.
   It creates `rinthel.db` and the first admin: copy the password it shows,
   it is not shown again.
2. **BOOT**: loads the model and builds/starts Understory and Deck.
3. **MONITOR**: confirms the services are up.
4. Open Deck at <http://127.0.0.1:4100> and log in as `admin` with that
   password. If you lost it: `python -m rinthel_tui.identity reset-admin`.
   Understory is at <http://127.0.0.1:3800>.

Linux starts with its Validated profile (`VALIDATED_PROFILES["linux"]` in
`rinthel_tui/config.py`). Close games or other RAM/VRAM-hungry applications
during the first run.

Deck keeps its state (`deck.db`, pi's home, Sessions) in `data/deck`; no
pre-existing pi folders are needed on the host.

## 4. Coming from an older layout

An older install is not migrated: the current layout does not read the old
root `.venv`, the old `.env` keys, nor another portal's data. Run a clean
INSTALL and delete by hand what is no longer used. INSTALL never deletes
anything. Stop everything first (**TERMINATE**, then
`rinthel/rinthel-boot.sh --stop`), and keep a copy of anything you still want
to read.

Git removes the files it tracked when you update; what stays behind is what
it never tracked. What the current layout uses at the root: `rinthel/`,
`deck/`, `understory/`, `docs/`, `scripts/`, `compose/` (Windows only),
`docker-compose.yaml`, the `.env`, `models.local.json`, `data/` and `logs/`.
Safe to delete:

- `.venv/` at the repository root: the venv is now `rinthel/.venv`.
- Build and cache leftovers of the old places: `rinthel-client/` at the root
  (its `target/` build; the client now lives in `rinthel/rinthel-client/`),
  `rinthel_tui/`, `tests/` and `hostexecd/` at the root if only
  `__pycache__` folders remain, and any `*.egg-info`.
- `model-profiles.json` and a `secrets/` folder at the root: the model picker
  is gone (the catalog is `models.local.json`) and nothing reads `secrets/`.
- The folder of the previous web portal at the root (its `node_modules` and
  build output are untracked), and its data folder in `data/`: in `data/`,
  everything except `deck/`, `understory/`, `hostexecd/`, `instance.toml` and
  `rinthel.db` belongs to the old layout. Its containers and images can go too
  (`docker ps -a`, `docker image ls`); the current compose project is
  `rinthel-general` (services `deck`, `understory`).
- In the root `.env`: start again from `.env.example` and carry over only what
  you set yourself (ports, paths of llama.cpp and the GGUFs). INSTALL writes
  the secrets again. Keys the current daemon no longer reads include
  `PORTAL_PASSWORD`, `OPENCODE_API_KEY`, `COMPOSE_FILE` on Linux and a
  hand-set `AUTH_TOKEN` (compose passes `UNDERSTORY_TOKEN` to Understory); the
  daemon warns about the legacy llama keys it still recognises.

llama.cpp and the GGUFs stay outside the repository (`~/llama.cpp` and the
paths in `models.local.json`): keep them.

## 5. Daily use and diagnosis

```bash
rinthel/rinthel-boot.sh
```

Use **BOOT** to start the services and **TERMINATE** to stop them.
`rinthel/rinthel-boot.sh --stop` stops only the control daemon; it does not
stop the containers nor the model.

```bash
curl -f http://127.0.0.1:8080/v1/models
docker compose ps
docker compose logs --tail 60 deck understory
tail -n 60 logs/daemon.log
tail -n 60 logs/llama-server.log
```

If Docker says permission denied, check that the session has the `docker`
group; restarting only the terminal may not apply it. If you installed Docker
after INSTALL, run it again so it writes `DOCKER_GID`. Do not use
`sudo rinthel/install.sh`: the data would end up owned by root.

To change the Local model, edit `models.local.json` and run
`python -m rinthel_tui.models use <id>` with the services stopped, or switch
from Deck's Ajustes ([`local-models.md`](local-models.md)).

## Tests

```bash
rinthel/.venv/bin/python -m pip install -e 'rinthel[dev]'
(cd rinthel && .venv/bin/python -m pytest -q)
bash -n rinthel/install.sh rinthel/rinthel-boot.sh
cargo test --locked --manifest-path rinthel/rinthel-client/Cargo.toml
```
