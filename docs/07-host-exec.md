# Host exec

Host exec lets the Agent of an **admin's** Session run shell commands on the
real host, outside Deck's container. It is Linux only: on Windows the daemon
never starts `hostexecd` and Deck never loads the tools.

## Pieces

| Piece | Where | What it does |
| --- | --- | --- |
| `hostexecd` | `rinthel/hostexecd/` | A small FastAPI process on `127.0.0.1:8766`: `POST /exec`, `GET /history` (both behind the token) and `GET /health` |
| `HOSTEXECD_SERVICE` | `rinthel/rinthel_tui/lifecycle/services.py` | `hostexecd` as a `LocalProcessService` of the daemon |
| Host exec tools | `deck/server/src/pi/host-exec/host-exec-tools.ts` | `rinthel_host_exec` and `rinthel_host_exec_history`, an inline factory of Deck's pi |

`hostexecd` runs what it is asked as the user that started the daemon,
without sudo. There is no allowlist of commands: the same freedom as `bash`,
on the host instead of the container. Anything that needs root fails on its
own. A call is blocking: it waits for the command (60 s by default, 600 s at
most) and answers its exit code, stdout and stderr, each cut at 50 kB.

## Lifecycle

`hostexecd` is a managed service of the daemon, like `llama-server`:

- **BOOT** spawns it after `llama-server` and before the Docker services, and
  waits for `GET /health`. **TERMINATE** stops whatever listens on its port.
  **RELOAD** does both.
- The **Monitor** shows it as a `hostexecd` row of `models_status.services`.
  On Windows the row is omitted.
- The daemon hands it, by environment, its port (`RINTHEL_HOSTEXECD_PORT`),
  the token (`RINTHEL_HOSTEXECD_TOKEN`) and the Instance root
  (`RINTHEL_INSTANCE_ROOT`). It reads no `.env` of its own.
- Its output goes to `logs/hostexecd.log`. Every `/exec` is audited, before
  its answer, as one JSON line in `data/hostexecd/audit.jsonl` (command, cwd,
  exit code, duration, output sizes, timeout). Both are git-ignored.

`rinthel-boot.sh` starts only the daemon; it keeps no pidfile for
`hostexecd`.

## Token and URL

1. **INSTALL** (`INSTANCE — token de host exec`) writes
   `RINTHEL_HOSTEXECD_TOKEN` in the root `.env` once
   (`rinthel_tui.install.host_exec.prepare_host_exec`). It keeps an existing
   token, adopts one exported in the shell, and stops without printing or
   rotating anything when the `.env` and the shell disagree. The token is not
   rotated from the TUI.
2. The **daemon** reads it with the rest of its config and passes it to
   `hostexecd` and to Deck.
3. When it brings **Deck** up, the daemon sets `RINTHEL_HOSTEXECD_URL`
   (built with `deck.host_address`: `http://127.0.0.1:8766` on Linux) and
   `RINTHEL_HOSTEXECD_TOKEN` in the environment of `docker compose`;
   `deck/docker-compose.yml` passes both to the container. Where `hostexecd`
   does not run (Windows, or `RINTHEL_HOSTEXECD_ENABLED=false`) both are
   empty, which wins over the root `.env`.

Without a token `hostexecd` authenticates nobody, and Deck loads no host exec
tools.

## In Deck

- **Admin only.** The factory is loaded only in a Session whose owner is an
  admin (the general `ToolProfile`); a member's closed profile never has the
  tools. Before every call the tool asks the daemon again whether the owner is
  an admin now; a member, a gone owner or no answer is a refusal, and nothing
  reaches the host.
- **Loading.** Without a token the tools are absent and the Session starts as
  usual. With a token, a registration that fails (a URL that cannot be
  `hostexecd`) stops the admin's Session from starting.
- **Guard.** Output of a network command run through `rinthel_host_exec`
  (`curl`, `wget`, mail clients) taints the Session. A tainted Session loses
  `rinthel_host_exec` and `rinthel_host_exec_history` whatever the input, for
  the rest of its life (`TAINT_REVOKED_TOOLS` in `deck/server/src/pi/guard.ts`).
  A new, clean Session has them again.
- If `hostexecd` is down or refuses the token, the call is an error the model
  reads; it is told to report it, not to retry.

Nothing of the host's own pi is shared: no extension path, bind mount or
Compose override carries host exec into Deck.

## Settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `RINTHEL_HOSTEXECD_PORT` | `8766` | Port of `hostexecd` on the host loopback |
| `RINTHEL_HOSTEXECD_ENABLED` | `true` (Linux), `false` (Windows) | Whether the daemon runs it; never on Windows |
| `RINTHEL_HOSTEXECD_TOKEN` | written by INSTALL | Shared by `hostexecd` and Deck |

## Validation

```bash
(cd rinthel && .venv/bin/python -m pytest -q tests/hostexecd tests/lifecycle/test_hostexecd_service.py)
(cd deck && npm run build -w @deck/canvas-catalog && node --import tsx --test tests/guard-host-exec.test.mts)
```

The tests use temporary roots: `hostexecd`'s routes are called in process
(harmless commands such as `echo`), and Deck talks to a fake `hostexecd`.
None starts a `hostexecd` process. Running a command on the host from
an admin Session is a manual item of
[`docs/testing/live-checklist.md`](testing/live-checklist.md).
