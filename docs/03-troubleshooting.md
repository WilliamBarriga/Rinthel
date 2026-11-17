# Troubleshooting

> [!NOTE]
> **"error: .venv/bin/python not found"** when running `rinthel-boot.sh`
> — you haven't created the venv, or you're running it from a different
> directory. Create the venv at the repo root (see `README.md` →
> Installation).

> [!WARNING]
> **Lost the admin password, or the daemon says "sin admin activo: corré
> reset-admin"** — there is no open mode and no password reset over HTTP.
> On the host, run
> `rinthel/.venv/bin/python -m rinthel_tui.identity reset-admin [--username admin]`:
> it makes that user an active admin with a new random password, printed
> once, and revokes their refresh tokens. It works with the daemon running
> or stopped.

> [!WARNING]
> **The daemon refuses to start: "rinthel.db has schema version N but this
> daemon knows up to M"** — `data/rinthel.db` was written by a newer
> version. Update the code; never downgrade the data. "SQLite X is too old"
> means the Python of the daemon ships an SQLite older than 3.37.

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

> [!WARNING]
> **Server dies right after enabling MTP** (`"mtp": true` in the active
> Local model, `cudaMalloc failed: out of memory` in
> `ggml_cuda_graph_evaluate_and_capture`) — MTP's compute buffer needs
> ~650 MiB that the current batch size is already using. Lower
> `--ubatch-size`/`--batch-size` to `1024` or `512` in
> `[N] CONFIGURAR > CÓMPUTO` (512 is the config with measured headroom for
> MTP), or activate an entry with `"mtp": false`. The config save warns
> about this combination before you get there.

> [!NOTE]
> **Binary or model not found** — the app warns on stderr at startup but
> doesn't block the menu. Adjust `RINTHEL_LLAMA_BIN` in `.env`; a missing
> GGUF, an unknown active id or a bad entry is a catalog problem
> (`models.local.json`, see [`local-models.md`](local-models.md)) and BOOT
> leaves `llama-server` out until it is fixed.

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

> [!WARNING]
> **Understory `memory_query` fails with `Connect Timeout Error
> (attempted address: host.docker.internal:8080)`** while
> `memory_status` works — the container can't reach llama-server. A
> timeout (not "refused") means a packet is being dropped on the host.
> 1. `docker exec rinthel-general-understory-1 nc -zv -w3 host.docker.internal 8080`
>    reproduces it.
> 2. `sudo iptables -t nat -S PREROUTING | grep 8080` — any `DNAT
>    --to-destination 127.0.0.1:8080` is a leftover of the old
>    `route_localnet` scheme and is the usual culprit: after the bridge is
>    recreated `route_localnet` resets to `0` and the kernel drops the
>    DNAT'ed SYN silently (no `[UFW BLOCK]` log). Delete it, and disable
>    `understory-llama-nat.service` if it exists.
> 3. `sudo ufw status | grep 8080` must include
>    `8080/tcp on br-rgunderstory ALLOW IN`.
>
> Setup and rationale: [`01-system-overview.md`](01-system-overview.md#understory--llama-server).

> [!NOTE]
> **Phone shows "offline" in `tailscale status` with no config change**
> — not a network issue, the app got killed in the background. Check
> battery optimization (and autostart, on MIUI/Xiaomi) for Tailscale.
