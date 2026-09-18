# A real browser for the agent

**Status:** design, not built.

## What this is for

The agent needs authenticated web access. Not "fetch a URL" — a logged-in
browser, with its own accounts, that stays logged in.

The premise is that **the agent is a teammate, not a proxy**. It has its own
Google account, its own logins. It is not acting on behalf of whoever is talking
to it, so browser access is a property of the agent's session, not of the
speaker's role. A colleague asking it to check something is asking a colleague
who has their own access.

The rule that follows: **no credential ever passes through the model.** A human
logs in once, by hand, in a visible browser. The profile persists. Every later
run drives that same profile and finds itself already signed in.

## Shape

```
┌─ portal container ────────┐     ┌─ browser container ───────────────┐
│  pi + MCP adapter         │     │  Chromium                          │
│    └─ playwright-mcp ─────┼─CDP─┼─▶ :9222 (127.0.0.1 only)          │
│  "Open browser" button ───┼─────┼─▶ :3001 KasmVNC — you, logging in │
└───────────────────────────┘     │  profile: /data/browser/default    │
                                  └────────────────────────────────────┘
                                                │
                                     allowlist proxy (:3128)
                                                │
                                            the internet
```

### A sidecar, not the portal image

The portal image is 1.06GB; Chromium plus a VNC stack roughly doubles it. A
separate service also means the browser can be restarted, or crash, without
taking the agent down. Both run with host networking, so `127.0.0.1` is the same
address on both sides.

Candidate base: `linuxserver/chromium` — Chromium with a KasmVNC web UI, a
persistent config directory, and `CHROME_CLI` for flags. The human-facing half
is the awkward part and that image already solves it.

### The agent drives it over CDP, through MCP

Chromium starts with `--remote-debugging-port=9222`. `@playwright/mcp` connects
with `--cdp-endpoint`, which attaches to the **running** browser rather than
launching its own — that is what makes it the logged-in one.

This needs no new tool plumbing in the portal. It is an entry in `mcp.json`, and
the browser arrives as MCP tools through the adapter we already have.

## Domain control

Asked for: allowed URLs, wildcard domains, or failing that a plain on/off.

Wildcards are possible. Two layers, and only one of them is real:

**A filtering proxy (real enforcement).** Chromium runs with
`--proxy-server=127.0.0.1:3128`. The proxy holds the allowlist —
`*.google.com`, `github.com` — and refuses everything else. HTTPS needs no
interception: a `CONNECT` carries the hostname, which is all a domain rule
needs. Enforced outside the browser, so nothing the agent does inside it
matters.

**Chromium managed policy (defence in depth).** `URLAllowlist` / `URLBlocklist`
in `/etc/chromium/policies/managed/`, read at startup, root-owned. Blocks
navigation natively and costs nothing.

Policy alone is not enough: an agent holding CDP can issue requests through the
`Fetch` and `Network` domains that a navigation policy does not cover. If the
allowlist is meant to hold, it has to be the proxy.

## What is on and off

Browser tools are **off by default**, per session, and turned on where wanted —
a session or a routine, the same shape as the injection-guard toggle. Not gated
on the speaker's role: the agent uses its own accounts and its own judgement,
which is the point.

Balanced by making it visible rather than restricted:

- **Every navigation is an audit row.** URL, session, when. This is the single
  cheapest safety feature here and the reason the on/off can be as loose as it
  is. "What did my agent look at this week" should be one page.
- The profile directory is a credential store. The guard's `read-credentials`
  rule should cover its path, so a tainted session cannot read the cookie jar
  and post it somewhere.

## The portal side

A **Browser** page:

- Status, and the profile's size on disk
- **Open browser** — the KasmVNC UI in a new tab, where you log in by hand
- The allowlist, editable
- Which sessions and routines currently have browser access
- Recent navigations, from the audit

## Risks, stated plainly

- **CDP is unauthenticated.** Anyone who reaches `:9222` owns the logged-in
  browser: reads the mail, acts as the agent. Bind it to `127.0.0.1`, never
  publish it, never put it behind a reverse proxy.
- **The profile is the crown jewels.** Live session cookies for the agent's
  accounts, sitting on the data volume. Back it up like a secret, or not at all.
- **The KasmVNC UI needs its own password** and belongs on Tailscale/LAN with
  the portal.
- **Injection while browsing is the worst case.** A page the agent reads can try
  to steer it, and the thing being steered now has accounts. The taint rules
  already refuse uploads and credential reads after untrusted content; the
  allowlist proxy is what stops exfiltration to somewhere new.
- **Disk:** the image is 4.6GB, not the 1–1.5GB estimated here. cortex has
  135GB free, and the service is opt-in so nobody else pays for it.

## Build order

1. The sidecar and the profile volume. Log in by hand through KasmVNC — confirm
   the session survives a restart.
2. The MCP entry over CDP. Confirm the agent lands on a page already signed in.
3. Per-session and per-routine toggle, defaulting off.
4. Navigation auditing.
5. The allowlist proxy.
6. The Browser page in the portal.

Steps 1 and 2 are the ones that prove the idea; the rest is the shape around it.

## Open questions

- **One profile or several?** Starting with one shared profile. Named profiles —
  work Google in one, a test account in another — are a follow-up, and change
  the toggle from a boolean to a choice.
- **Which proxy?** A dozen lines of Node handling `CONNECT` against a list is
  enough and has no dependencies; squid or tinyproxy is more machinery than the
  rule deserves.
- **Does the agent get its own accounts created for it**, or share existing
  ones? The design assumes its own — that is what makes the teammate framing
  hold, and what keeps a colleague's request from reaching your personal mail.
