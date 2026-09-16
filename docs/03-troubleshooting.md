# Troubleshooting

> [!NOTE]
> **"error: .venv/bin/python not found"** when running `rinthel-boot.sh`
> — you haven't created the venv, or you're running it from a different
> directory. Create the venv at the repo root (see `README.md` →
> Installation).

> [!TIP]
> **Port already in use** — BOOT won't relaunch `llama-server` if
> something is already listening on `RINTHEL_LLAMA_PORT` (default
> `8080`); use RELOAD or TERMINATE first, or change the port in `.env`.

> [!WARNING]
> **"llama-server died instantly"** — almost always an invalid flag or
> the model/binary don't actually exist; check the log at
> `RINTHEL_LLAMA_LOG_PATH` (default `logs/llama-server.log`).

> [!WARNING]
> **`CUDA error: out of memory` on the first real request** (not on
> startup, but as soon as a normal-sized prompt comes in) — almost always
> the context window (`-c`), the batch size, or the expert cache asking
> for more VRAM than is actually free. See
> [`02-hardware-optimization.md`](02-hardware-optimization.md) for the
> ~300 MiB safety margin and which flag to lower first.

> [!NOTE]
> **Model/binary not found** — the app warns on stderr at startup but
> doesn't block the menu; adjust
> `RINTHEL_LLAMA_BIN`/`RINTHEL_LLAMA_MODEL_PATH` in `.env`.

> [!IMPORTANT]
> **Docker daemon not running** — the BOOT phase detects it and stops
> with instructions (`sudo systemctl start docker`) before touching
> anything else.

> [!TIP]
> **Tailscale connects but the port doesn't respond (same wifi)** —
> `ufw` filters by subnet (e.g. `192.168.1.0/24`), and that traffic
> arrives with a source IP from Tailscale's range (`100.x.x.x`), not your
> LAN, even though it's on the same physical network. Add `sudo ufw allow
> in on tailscale0 to any port <port>` instead of (or in addition to) the
> subnet rule.

> [!NOTE]
> **Phone shows "offline" in `tailscale status` with no config change**
> — not a network issue, the app got killed in the background. Check
> battery optimization (and autostart, on MIUI/Xiaomi) for Tailscale.
