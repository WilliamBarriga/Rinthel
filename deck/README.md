# Deck

The web portal of a Rinthel Instance: login with a Rinthel user, Sessions
with the [pi coding agent](https://github.com/earendil-works/pi), chat,
Canvases, voice, the Instance browser and the admin's Ajustes. Built to be
left alone: **give the Agent a task, close the browser, come back later and
read what it did.**

Runs are owned by the server, not by the tab. Every event pi emits is appended
to the Session's log in `deck.db`, so reconnecting replays exactly what was
missed (`?since=` the last event id) and then continues live. Submitting a
prompt returns as soon as pi accepts it; the run goes on server-side.

## Quick start

The Rinthel daemon builds and starts Deck (**BOOT**, from the root
`docker-compose.yaml`) and the root `.env` configures it. Open
<http://127.0.0.1:4100> and log in with a Rinthel user (INSTALL creates the
first admin); Deck validates the daemon's Panel token
(`RINTHEL_PANEL_SECRET`) and refuses to start without it.

On Linux the container uses the host network, so pi reaches the services on
the box (`llama-server` on `127.0.0.1:8080`) as it would outside a container.
On Windows it runs in a bridge network with its port published on the
loopback only ([`docs/04-windows-installation.md`](../docs/04-windows-installation.md)).

## How it works

```
Browser ──SSE (replay + tail)──▶ Deck server ──pi SDK, in process──▶ the Session's Agent
                                     │                                   │
                                     └─▶ deck.db (SQLite)               └─▶ llama-server (route from the daemon)
```

- **One Local model for every Session.** Deck never picks a model: each call
  goes straight to the `llama-server` the daemon routes it to
  (`GET /model-provider/routing`), with the Session's own slot saved and
  restored around it. Only an admin switches the Local model, or turns the
  Instance's voice on or off, in Ajustes.
- **What each Session may call** is decided by `ToolProfile`
  (`server/src/tool-profile.ts`) from its owner's live role: an admin gets the
  general Agent (pi's tools, the agentDir's extensions and skills, the skills
  Deck ships in `skills/`, host exec, subagents, Memoria, the Instance
  browser); a member gets a closed profile with only the Canvas tools and the
  Instance SOUL. An owner that is gone, or an identity that does not answer,
  stops the Session: nothing falls back to the general Agent.
- **The Guard** runs in every Session, taints a Session that reads untrusted
  content and then refuses the dangerous shapes of a call; a tainted Session
  loses host exec, subagents and Memoria writes.
- **Extras** are pi packages an admin installs into the agentDir on the volume
  through `/api/packages`; what Deck needs travels in its image.

pi has no approval prompts: it runs with the permissions of its process. That
is why every request needs a logged-in Rinthel user and why Deck should stay
on the loopback, a LAN or a VPN, never the public internet.

## Configuration

Every variable, the state on the volume (`data/deck/`: `deck.db`, pi's home,
Sessions, slots) and each surface are in
[`docs/deck/configuration.md`](../docs/deck/configuration.md); the layers,
ports and guards in [`docs/deck/architecture.md`](../docs/deck/architecture.md).

## Limitations

- A run does not survive a **Deck restart**, only a browser disconnect. pi
  keeps its session files, so the conversation is intact and can be continued,
  but the run in flight stops (the Session shows as interrupted).
- Two Sessions on the same workspace edit the same working tree.

## Tests

```bash
npm test               # server, web (vitest), the guards and the HTTP tests in tests/*.test.mts
npm run test:browser   # Playwright specs in tests/browser/ (Chromium)
```

`npm test` builds the server first. The HTTP tests run the real
`createDeckApp` over a fake daemon, a fake `llama-server` and the other fakes
in `tests/helpers/`; nothing reaches a real Instance, model or package
registry. The browser specs cover only what needs a real browser (history,
reload, focus and keyboard, storage, audio, the browser panel). There is no
CI: run both by hand. The guards (`tests/domain-imports.test.mts`,
`tests/import-cycles.test.mts` and the rest) are part of `npm test`.
