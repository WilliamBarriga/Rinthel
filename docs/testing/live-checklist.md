# Live checklist (pre-merge)

Runbook to try a branch against real hardware before merging. It keeps no
state: each run is noted in the PR (or the commit message) with date, commit
and findings (template at the end).

It has two parts: the automated suite (section 1) and a short manual list
(section 2). **An item is manual only for one of these three reasons, and each
item says which:**

1. **Human perception:** something has to be judged by eye (phase order, a
   readable error, a banner).
2. **Destructive host state:** it stops, recreates or rebuilds something of the
   real Instance, or needs `sudo`. The suite cannot do it without breaking the
   stack it shares or touching real data.
3. **Needs a human actor:** a microphone, a real phone, the operator's OK to
   put a model on the GPU.

Everything else goes to a suite. If an item fits none of the three, it is not
added here: a test is written instead.

## Prerequisites

**Phase 1: `pytest -m live`**
- **Python venv with the dev dependencies** (`pip install -e "rinthel[dev]"`).
- **A llama-server binary and a GGUF** for the two tests that need a real
  model (`--start-llm`). They are read from the real Instance's `.env` and
  active Local model (`RINTHEL_LLAMA_BIN`, `models.local.json`, `data/instance.toml`);
  the real files are only *read*. To use another model (for example a small
  one when the GPU is busy) set `RINTHEL_LIVE_GGUF=/path/model.gguf` and,
  optionally, `RINTHEL_LIVE_CONTEXT=<tokens>` (default 8192).
- **Free GPU memory for a second llama-server.** The suite starts its own on a
  free port, next to the real Instance's one if it is running. If the model
  does not fit twice, stop the Instance first or use `RINTHEL_LIVE_GGUF`.
- **Nothing else is needed from the real Instance.** Every test daemon runs on
  a temporary root `/tmp/rinthel-live-*` with its own `.env`, its own
  `rinthel.db` and its own free ports. It never reads or writes the real
  `data/`, `logs/` or containers, and it never kills by a real Instance's port.
- **llama-server is never started on its own.** The tests that need one fail
  (they do not skip: a false green is worse than a red) unless `--start-llm`
  is passed, which is the operator's explicit OK to use the GPU.

**Phase 2: manual list**
- **A real daemon up** with the real `.env` (`./rinthel/rinthel-boot.sh`), except
  in the items that start with the Boot.
- **Deck up** with two users: an `admin` and a `miembro`.
- **The live suite already passed**, and nobody else uses the Instance while
  the list is walked (several items stop or recreate real services).

## The three runs

```bash
# 1. Python suite: contract and HTTP/WS tests, no real processes (live is excluded)
cd rinthel && python -m pytest -q

# 2. Deck: unit tests, then browser tests against the fake Deck server
#    (headless Chromium, free ports, no daemon and no model; `npx playwright install chromium` once)
cd deck && npm test && npm run test:browser

# 3. Live: the real daemon, by hand
cd rinthel && python -m pytest -m live                  # daemon only, no model
cd rinthel && python -m pytest -m live --start-llm      # plus real llama-server
```

Run 3 has no CI: it runs by hand, on Linux, before merging a change to the
daemon, the lifecycle or Local models. Deck's opt-in
`live-transcription.test.mts` (a real whisper server, Linux only) is run
by hand from `deck/` in the same pass; the Deck package documents its command.

## 1. Automated suite

`pytest -m live --start-llm` has to pass entirely before continuing.

When it ends the suite checks by itself that nothing was left behind
(directories `/tmp/rinthel-live-*` and containers `rinthel-live-*`) and fails
if there is something. If a run died halfway, `--sweep-leftovers` removes, on
the next start, what it left. The sweep matches only direct children of `/tmp`
named `rinthel-live-<something>` (never a symlink) and containers whose name
starts with `rinthel-live-`; it is opt-in because it recognises by prefix, not
by run, so it would also take a parallel run's leftovers.
`tests/live_harness/test_garbage.py` pins those matchers with hostile names.

It covers:
- the Access policy (a member is not an admin, a disabled admin or a disabled
  user acted for by Deck is rejected with a live token, an empty service
  secret lets nobody through) — `test_access_policy.py`;
- the health of the daemon: opening and closing the Monitor leaves no orphan
  `docker compose ps`, a Ctrl+C shutdown is clean, and every test daemon fails
  at shutdown if its `daemon.log` has a `Traceback` — `test_daemon_health.py`;
- the Monitor over the real WS: the five streams, the echo of a `log_line`,
  and (with `--start-llm`) the `llm` line of `models_status` turning ready
  with a real llama-server — `test_monitor_ws_live.py`;
- the rotation of the service and Panel secrets — `test_secret_rotation.py`;
- **the Local model switch against a real llama-server** (`--start-llm`) —
  `test_model_switch.py`: `POST /models/activate` kills the old llama-server
  and spawns the new model (the listener PID changes, routing and `/models`
  follow); and a model that cannot load (a file with the GGUF magic and
  garbage) makes the new server exit, the daemon restarts the previous model
  (`rolled_back: true`) and it keeps serving.

The model switch runs against a llama-server on a free port of its own, so the
switch only ever kills what the test started.

### What left the checklist and where it lives now

These items are no longer walked by hand:

| Item | Where it is tested |
|---|---|
| No orphan `docker compose ps` after opening and closing the Monitor | `tests/live/test_daemon_health.py`; the `ps` cancellation itself in `tests/monitoring` |
| Shutdown without `Traceback` | `tests/live/test_daemon_health.py` and the `daemon.log` check of every test daemon (`tests/live/conftest.py`) |
| Local model switch: kill, spawn, rollback | `tests/live/test_model_switch.py` (real llama-server) and `tests/daemon/test_models_endpoints.py` (doubles) |
| Recovering the admin without reinstalling (`reset-admin`) | `tests/identity` |
| `hostexecd` contract | `tests/hostexecd`, `tests/lifecycle/test_hostexecd_service.py` and Deck's `tests/guard-host-exec.test.mts` (there is no live for it; the manual item below covers the real host) |

## 2. Manual list

Each item says why it is manual (reasons 1, 2 and 3 above), the steps and what
to look at. Note done or failed and the detail. An item that was not walked is
noted as **skipped**, not as done.

### Lifecycle with real Docker

- [ ] **Boot via `./rinthel/rinthel-boot.sh`** with the real `.env`. *Manual (2):
  it starts the real stack with the real config.* The daemon starts (pidfile),
  the TUI connects and the Boot leaves up the enabled Docker services and the
  managed services.
- [ ] **Terminate.** *Manual (2): it stops the real stack.* Everything stops;
  the Monitor shows the services down.
- [ ] **Reload.** *Manual (2): it rebuilds real images and recreates real
  containers.* After a change under `rinthel/`, a Reload leaves the services
  running the new code.
- [ ] **Docker off at Boot.** *Manual (2 and 1): it needs `sudo systemctl stop
  docker.socket docker` (and `start` afterwards) and a human reading the
  error.* The Boot stops with a readable error and starts nothing.

### Voice (Linux, opt-in)

- [ ] **INSTALL with voice on an existing Instance.** *Manual (2): it builds
  whisper.cpp and audio.cpp, downloads real models and loads one on the GPU.*
  With the stack booted, `rinthel/.venv/bin/python -m rinthel_tui.install --voice`
  ends with every unit `ok`; the Monitor shows `stt` and `tts` ready, and
  `GET /model-provider/routing` carries both. Run it again: nothing is rebuilt
  or downloaded and both stay running.
- [ ] **Voice off and back.** *Manual (2): it stops a real service.* Turning
  `tts` off (`POST /models/off` from Deck, or `models off tts` with the
  services stopped) frees port `7860`; the next Boot leaves `audiocpp-server`
  out; activating `pocket-tts-es` again brings it back.

### TUI

- [ ] **`phase_*` progress** of Boot, Terminate and Reload. *Manual (1): order
  and markers are seen, not counted.* Phases in order, markers between the
  Reload batches.
- [ ] **Outcomes and errors.** *Manual (1): "readable" is a human judgement.*
  A failure shows as a readable error, not a raw trace.
- [ ] **The Local model line of the Monitor.** *Manual (1): it is read on
  screen.* While an admin switches the Local model from Deck, the Monitor shows
  the `llm` line of `models_status` going down and up with the new model.
  With voice active, the `stt` and `tts` lines show their model and state.

### Deck (web)

What the Playwright suite already covers (the happy path against the fake
Deck server) is not repeated. These items are what it cannot see: the
interface with the real daemon, model and host, and how it looks.

- [ ] **Login and sign out.** *Manual (1): each screen state is looked at.* A
  wrong password (readable error) and `admin`. With `miembro` the
  administration entries disappear. `Sign out` goes back to the login and F5
  does not reopen the session.
- [ ] **Real conversation.** *Manual (1 and 3): the answer is read and
  `--start-llm` occupies the GPU.* A new Session with `admin` and another with
  `miembro`: the bar under the composer shows the model; the answer streams;
  closing the tab mid-turn and reopening restores what was lost without
  duplicating. Deleting the Session deletes its Slot file. While llama-server
  reads a long prompt the chat shows its progress, and the window under the
  composer is the Local model's (`context_window` of the catalog).
- [ ] **Local model switch from Deck.** *Manual (1 and 3): the message is read,
  and two models occupy the GPU in turn.* With `admin`, switch from the
  composer while a member's turn is answering: a 409 says there are turns in
  course and nothing changes. Switch again once it ends: the member's next
  message is answered by the new model, and the window under the composer
  changes. The same switch from Ajustes; `miembro` sees neither.
- [ ] **Canvases and the Instance SOUL.** *Manual (1 and 3): the Agent writes
  with the real model, and what it builds is looked at.* In a `miembro` Session
  ask for a document and then for a form: the panel opens by itself, the
  `ui` canvas takes typed fields and its button leaves a message that the next
  answer takes into account (the click alone starts no turn). The Agent of that
  Session answers as the Instance SOUL says, and as `admin` editing the SOUL
  changes the next Session of the member; `miembro` reads it read-only. After
  a fresh INSTALL `data/deck/instance/SOUL.md` exists, and a second INSTALL
  leaves an edited one alone.
- [ ] **Instance browser.** *Manual (2 and 1): it pulls and runs the real
  `deck-browser` container and a real Chromium.* Only `admin` sees Instance
  browser. Installing without a password is refused; with one (suggested is
  fine) it runs, and the live view opens over HTTPS (or on localhost). In an
  admin Session with the browser on, the Agent navigates a page (the first
  call fetches `@playwright/mcp`), a snapshot and a screenshot come back, and
  clicking and typing work with the view closed (the frame keeper keeps it
  rendering). With the toggle off, or in a `miembro` Session, the call is
  refused and nothing reaches the browser. Two admin Sessions see the same
  tabs. Left alone for an hour it is still running; Stop and Start keep the
  logins. Optional: `BROWSER_EXTERNAL=true` against a Chrome started by hand
  with `--remote-debugging-port=9222` shows as external and cannot be stopped
  from Deck.
- [ ] **Terminal (admin only).** *Manual (2): it opens a real pty on the host.*
  The Session terminal opens, takes commands and closes without leaving the
  process. `miembro` does not see it.
- [ ] **Voice, theme and settings.** *Manual (1 and 3): it needs a microphone.*
  The voice adapter records and transcribes a sentence; the theme selector
  switches light/dark without breaking the layout, also at phone width.

### Logs

- [ ] **Rotate or delete `logs/llama-server.log`** with the TUI on the logs
  screen. *Manual (1): it is what is seen on screen; the backend is tested.* The
  50-line backlog is not resent and new lines keep arriving when the file
  returns.

### Secrets

- [ ] **Rotate `RINTHEL_SERVICE_SECRET` from Settings.** *Manual (2): it acts on
  the real daemon, and the suite's daemons are throwaway.* The TUI adopts the
  new secret without restarting: Monitor and Boot keep working. Deck, which
  reads the secret from its environment, needs the documented restart.

### Shutdown

- [ ] **`./rinthel/rinthel-boot.sh --stop`.** *Manual (2): it stops the real
  daemon.* It sends SIGTERM, the daemon closes without `Traceback` in `logs/`
  and the script removes the pidfile. Ctrl+C is already proven by the suite;
  this covers the script and the signal.

### hostexecd

- [ ] **Host-exec on the real host.** *Manual (2 and 3): it runs a command on
  the real host from a real admin.* After BOOT, the Monitor shows `hostexecd`
  online. From a clean admin Session, ask for a harmless command (`uname -a`);
  it runs on the host and shows in `data/hostexecd/audit.jsonl`. A member's
  Session has no host exec tools, and an admin Session that read a web page
  through `curl` is refused. After TERMINATE nothing listens on `:8766`.

## Run template

```markdown
## Live run — <date> · <short commit>

- `pytest -m live --start-llm`: <N passed | failures>
- Manual: <all done | list of failures with detail>
- Skipped: <none | item and why>

### Findings
- <finding> → <fixed in <commit> | open>
```
