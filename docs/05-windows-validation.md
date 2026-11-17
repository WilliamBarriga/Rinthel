# Validating Rinthel on Windows

This document records the reproducible point reached on 2026-09-20. It is not
a performance promise for any PC: it is evidence from one machine, one model
and one concrete profile.

## Reference machine

| Component | Observed value |
|---|---|
| System | Windows 11, 64-bit PowerShell, Docker Desktop with Linux containers |
| CPU | AMD Ryzen 7 260, 8 cores / 16 threads |
| Visible RAM | 31.31 GiB |
| GPU | NVIDIA GeForce RTX 5070 Laptop GPU |
| VRAM | 8151 MiB |
| NPU | AMD XDNA, up to 16 TOPS, detected but not used by CUDA `llama.cpp` |
| Model | Qwen3.6-35B-A3B UD-Q4_K_XL, 21.28 GiB |

The exact configuration is in
[`windows-hardware-optimization.md`](windows-hardware-optimization.md). Local
files live by default under `%USERPROFILE%\Rinthel-data`; no user path,
password or token is part of the repository.

## Validated architecture

- Ratatui client, FastAPI daemon and `llama-server.exe`: native Windows
  processes.
- Understory and the web portal: Linux containers in Docker Desktop.
- `llama-server`: `127.0.0.1:8080` on the host.
- Understory: `127.0.0.1:3800`.
- Web portal: `127.0.0.1:4100`.
- The portal reaches the model at `http://host.docker.internal:8080/v1`.

The validation was done with the previous web portal, which Deck replaced.
Deck talks to the same `llama-server` with the same argv of the Validated
profile (the change is in the client, not in inference), so the measurements
below still hold. Deck on Windows (`compose/windows.override.yaml`: bridge
network, port published on the loopback) is not validated on this machine
yet: see the [Windows checklist](#windows-checklist).

## Where the profile lives

Since the model became a Local model of the catalog, the hardware values of
the Windows Validated profile live in one place,
`rinthel_tui/config.py::VALIDATED_PROFILES["windows"]`, and the 65,536-token
window in the default entry INSTALL writes to `models.local.json`.
`install.ps1` does not write the profile to `.env`. The `llama-server` argv is
still identical to the validated one and is pinned by
`rinthel/tests/models/test_validated_profile.py`; that is why neither the
move to Deck nor the Windows override asks for a new benchmark. Any change to
that argv does.

The lifecycle uses Windows adapters of its own (`WindowsRunner`,
`WindowsProcesses`, `WindowsHostInfo`: `creationflags`, stopping the process
tree with psutil, discovery of Visual Studio's CMake, `CUDA_PATH` and
`Release`). They run on Linux under the same contract suites as the POSIX
ones, with `creationflags=0`; their real behaviour on Windows is still
pending manual verification on the reference machine.

## Problems solved

1. Early refusal of x86 PowerShell and robust detection of Python 3.13.
2. Discovery of the CMake installed with Visual Studio, and of CUDA through
   `CUDA_PATH` or the standard paths.
3. Multi-configuration `Release` build of `llama.cpp` and the right location
   of `llama-server.exe`.
4. Persistent daemon start with a pidfile, hidden window and local logs.
5. Cross-platform stop of services by port through `psutil`.
6. Docker Desktop check with `docker info`, without depending on
   `systemctl`.
7. WebSocket transport declared as a runtime dependency.
8. The web portal's local provider wired to the host's model, removing the
   accidental dependency on OpenRouter.
9. A separate `install-status.ps1` monitor for build, download and
   completion.

## Observed performance

Five document queries and one guardrail correction were run in one session
of the previous web portal. The accumulated context reached 15,526 tokens
with no CUDA error and no loss of the document.

| Test | Output | Time | Approx. speed | Reviewed quality |
|---|---:|---:|---:|---:|
| Reading and summary | 878 tokens | 28.1 s | 32.6 tok/s | 9/10 |
| Catalog and prices | 1031 tokens | 31.0 s | 33.2 tok/s | 8.5/10 |
| Missing data and margins | 866 tokens | 26.4 s | 32.8 tok/s | 10/10 |
| Commercial answer | 1282 tokens | 40.5 s | 31.7 tok/s | 9.5/10 |
| Validity and contradictions | 1349 tokens | 42.5 s | 31.7 tok/s | 9/10 |
| Correction with a guardrail | 1828 tokens | 55.6 s | 32.9 tok/s | 10/10 |

Reviewed average: 9.3/10 quality and about 32.5 tokens/s. Quality is a human
assessment of these tests, not a universal metric.

### Controlled load

A direct generation of 420 tokens took 13.994 s (30.0 tok/s), with twelve
hardware samples:

| Resource | Average | Relevant peak or minimum |
|---|---:|---:|
| CPU | 59.5% | 74.5% peak |
| Used RAM | 29.47 GiB | 29.57 GiB peak; 1.74 GiB free minimum |
| `llama-server` working set | — | 17.03 GiB peak |
| GPU | 39.9% | 81% peak |
| Used VRAM | 7341 MiB | 551 MiB free minimum |
| GPU temperature | — | 58 C peak |
| GPU power | — | 45.04 W peak |

The NPU shows up as `NPU Compute Accelerator Device`, but this server was
built with CUDA and gives it no work. Its 16 TOPS do not add to the VRAM or
to the CUDA capacity.

## Validated use cases

- Querying a local knowledge base with section citations.
- Retrieving catalog, prices, states and historical data.
- Refusing calculations when costs or variables are missing.
- Commercial drafts without inventing shipping, lead times or conditions.
- Detecting contradictions between current and historical prices.
- Separating active catalog, validation, experiment and proposal.

The same pattern applies to a small business, a labour-mobility operation or
a law firm: each organisation keeps its own knowledge workspace and rules. In
legal or migration domains the answers are documentary support and need
professional review; they do not replace legal advice or an official
decision.

## Recommended guardrail

The guardrail as it was tested (in Spanish, the language of the session):

```text
No conviertas inferencias en hechos confirmados.

Distingue siempre entre:
- Catálogo formal.
- Producto en validación.
- Concepto experimental.
- Información histórica.
- Información no documentada.
- Propuesta o recomendación creada por ti.

Si una acción parece razonable pero no está expresamente indicada en la base
de conocimiento, identifícala como “Propuesta”, no como política vigente.
```

The later test showed that this guardrail corrected an earlier inference
about the channel for shipping quotes and turned it explicitly into a
proposal.

## Windows checklist

Deck on Windows is verified on Linux only by tests: `docker compose config`
over the root compose plus `compose/windows.override.yaml`
(`rinthel/tests/test_windows_compose.py`), INSTALL's `COMPOSE_FILE`
(`rinthel/tests/lifecycle/test_install.py`), the `.ps1` contracts
(`rinthel/tests/test_windows_scripts.py`), the journal-mode check of
`deck.db` and the browser container's network (`deck/server/test/`). Every
item below is **not verified** until it is run on the reference machine.
Record the date, the Docker Desktop version and the result next to each one.

1. **Compose selection.** After INSTALL, the root `.env` has
   `COMPOSE_FILE=docker-compose.yaml;compose/windows.override.yaml` and
   `COMPOSE_PATH_SEPARATOR=;`. At the root, `docker compose config --quiet`
   succeeds and `docker compose config` shows `deck` without `network_mode`,
   with port `127.0.0.1:4100` and `DECK_DB_JOURNAL_MODE: delete`.
2. **Deck on the loopback.** After BOOT, `http://127.0.0.1:4100` answers on the
   host, and Deck is not reachable from another machine on the LAN.
3. **`host.docker.internal`.** From the Deck container,
   `http://host.docker.internal:8765/docs` (the daemon) and
   `http://host.docker.internal:8080/health` (`llama-server`) answer, both
   bound to `127.0.0.1` on the host. A chat turn in a Session reaches the model
   (the route the daemon hands Deck uses `deck.host_address`).
4. **`deck.db` in `DELETE`.** Deck's startup log (`docker compose logs deck`)
   shows `store: /data/deck.db (journal mode delete)`; there is no
   `deck.db-wal` under `data\deck`; Sessions survive `docker compose restart
   deck`.
5. **Understory over the shared network (Memoria).** An admin's Session
   reaches Understory at `http://understory:3800` with `UNDERSTORY_TOKEN`:
   `understory_memory_query` answers, and a wrong token gets 401. Understory
   is published on `127.0.0.1:3800` only and reaches `llama-server` through
   `host.docker.internal` (`host-gateway`). The fixed subnet
   `172.30.99.0/24` of `understory-net` does not clash with Docker Desktop's
   networks.
6. **Docker socket and `DOCKER_GID` under Docker Desktop.** Deck runs as the
   image's user with no `group_add` (`DOCKER_GID` is Linux only) and can use
   `/var/run/docker.sock`: the Instance browser screen shows docker mode, and
   Instalar pulls the image and creates `deck-browser`. If the socket is
   refused, record the socket's owner and mode inside the container.
7. **Instance browser in docker mode.** `deck-browser` runs on the
   `rinthel-general_deck_browser` network (`docker inspect deck-browser`),
   nothing of it is published on the host, and from Deck:
   - CDP at `http://deck-browser:9222/json/version` answers. Two known risks,
     to confirm or rule out: Chrome's DevTools HTTP endpoint refuses a `Host`
     header that is neither an IP nor `localhost`
     (https://chromium.googlesource.com/chromium/src/+/master/content/browser/devtools/devtools_http_handler.cc),
     so a container name may be refused; and whether the image's Chromium
     honours `--remote-debugging-address=0.0.0.0` in a headful session. If
     either fails, record it; the fallback is `BROWSER_CDP_URL` with the
     container's IP on that network.
   - The live view at `/browser-ui` (the container's `3011`) opens, and the
     frame keeper's stream (`8082`) keeps the page rendering: a click by the
     Agent completes while nobody watches the view.
8. **Local or external browser.** With `BROWSER_EXTERNAL=true` and
   `BROWSER_CDP_URL=http://host.docker.internal:9222` (Chrome started on the
   host with remote debugging), the Instance browser screen shows it running.
9. **Omitted on Windows.** `MONITOR` lists no `hostexecd`, `stt` or `tts`;
   INSTALL with `--voice` shows only the Linux-only notice; an admin's
   Session has no host exec tools.
10. **TLS mount.** With no `PORTAL_TLS_DIR`, the `/dev/null` bind of the
    certificates does not stop Deck from starting under Docker Desktop.

## Pending limits

- The full 65,536-token context has not been filled or validated.
- RAM and VRAM headroom is small; raising context, batch, MTP or the expert
  cache needs an isolated benchmark.
- A fluent answer can contain a wrong inference. Flows that promise prices,
  logistics, legal requirements or external actions must keep human review.
