import { spawn, type ChildProcess } from "node:child_process";
import { randomUUID } from "node:crypto";
import express, { type Router } from "express";
import { getSession } from "../db.js";

/**
 * A shell, in the portal.
 *
 * Over a real pty rather than plain pipes, because a shell without one lies
 * about being interactive: no prompt, no colours, no job control. `script` from
 * util-linux allocates one and is already in the image, which beats a native
 * dependency for a feature this small.
 *
 * Output goes out over SSE and input comes back as POSTs — the same shape as
 * the session event stream, and no websocket library to add.
 *
 * This is shell access to the container for anyone holding the portal
 * password. That is already true of every session — the agent has bash — so it
 * grants nothing new, but it is worth being clear that it is not a lesser
 * thing than the chat box beside it.
 */

const MAX_SCROLLBACK = 200_000;

interface Term {
  id: string;
  proc: ChildProcess;
  /** Replayed to a client that connects late, so a reload keeps the screen. */
  buffer: string;
  listeners: Set<(chunk: string) => void>;
  exited: boolean;
}

const terms = new Map<string, Term>();

function create(cwd: string): Term {
  const id = randomUUID().slice(0, 8);
  // -q quiet, -f flush on every write so output is not held back, -e return the
  // command's exit status, and /dev/null because we want the pty, not a log.
  const proc = spawn("script", ["-qfec", process.env.SHELL || "bash -il", "/dev/null"], {
    cwd,
    env: { ...process.env, TERM: "xterm-256color" },
    stdio: ["pipe", "pipe", "pipe"],
  });

  const term: Term = { id, proc, buffer: "", listeners: new Set(), exited: false };

  const push = (chunk: Buffer) => {
    const text = chunk.toString("utf8");
    term.buffer = (term.buffer + text).slice(-MAX_SCROLLBACK);
    for (const l of term.listeners) l(text);
  };
  proc.stdout?.on("data", push);
  proc.stderr?.on("data", push);
  proc.on("exit", () => {
    term.exited = true;
    for (const l of term.listeners) l("\r\n[session ended]\r\n");
  });

  terms.set(id, term);
  return term;
}

export function terminalRouter(): Router {
  const router = express.Router();

  /** Opens a shell, in the workspace of a session when one is named. */
  router.post("/terminal", (req, res) => {
    const sessionId = typeof req.body?.sessionId === "string" ? req.body.sessionId : "";
    const cwd = (sessionId && getSession(sessionId)?.workspace) || process.env.HOME || "/";
    const term = create(cwd);
    res.json({ id: term.id, cwd });
  });

  router.get("/terminal/:id/stream", (req, res) => {
    const term = terms.get(req.params.id);
    if (!term) return res.status(404).end();

    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    });

    const send = (chunk: string) => res.write(`data: ${JSON.stringify(chunk)}\n\n`);
    // What is already on screen, so reconnecting does not show an empty shell.
    if (term.buffer) send(term.buffer);
    term.listeners.add(send);
    req.on("close", () => term.listeners.delete(send));
  });

  router.post("/terminal/:id/input", (req, res) => {
    const term = terms.get(req.params.id);
    if (!term || term.exited) return res.status(404).json({ error: "No such terminal" });
    if (typeof req.body?.data === "string") term.proc.stdin?.write(req.body.data);
    res.json({ ok: true });
  });

  /**
   * Tell the pty its new size.
   *
   * Written as a command rather than an ioctl: there is no pty handle here to
   * resize, but there is a real tty on the other end, and stty is how you tell
   * one how big it is.
   */
  router.post("/terminal/:id/resize", (req, res) => {
    const term = terms.get(req.params.id);
    const rows = Number(req.body?.rows) || 24;
    const cols = Number(req.body?.cols) || 80;
    if (!term || term.exited) return res.status(404).json({ error: "No such terminal" });
    term.proc.stdin?.write(`stty rows ${rows} cols ${cols} 2>/dev/null\n`);
    res.json({ ok: true });
  });

  router.delete("/terminal/:id", (req, res) => {
    const term = terms.get(req.params.id);
    term?.proc.kill("SIGHUP");
    terms.delete(req.params.id);
    res.json({ ok: true });
  });

  return router;
}
