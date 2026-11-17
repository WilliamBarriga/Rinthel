import http from "node:http";
import { randomBytes } from "node:crypto";
import type { AddressInfo } from "node:net";
import type { ModelRouting, Route } from "./model-routing/model-routing.js";
import { slotName, type SessionSlots, type SlotTurn } from "./session-slots/session-slots.js";
import type { PrefillEvent } from "@deck/contract";

/**
 * The one way a Session's pi reaches its Local model (ADR 0008).
 *
 * pi is pointed at `/s/<token>` on loopback with a dummy key. Every call reads the route again
 * (`GET /model-provider/routing`, one Local model per Instance) and goes straight to that
 * llama-server: no passthrough, no credential to add. On the way it asks llama-server for prefill
 * progress (`return_progress`) and reports what the stream says, and it holds the Session's slot
 * (`SessionSlots`) from the restore before the call to the save after it.
 *
 * When the admin switched the Local model since the Session last asked, the call is answered
 * `409 wrong_model` and the Session moves to the new route: pi's provider (`rinthel-provider.ts`)
 * retries the turn on the new model. With no Local model to route to the call is a 503.
 *
 * The token is random, not the Session id, so a Session cannot reach `/s/<another>` by guessing.
 */

export type Prefill = PrefillEvent;

/** What a Session's pi needs to reach its model. */
export interface ModelAccess {
  /** Where pi sends this Session's calls; the format's own path goes after it. */
  url: string;
  /** The route the Session talks to now: read at open, and again whenever a call found it moved. `null`: no Local model. */
  route(): Route | null;
}

interface Session {
  sessionId: string;
  ownerUserId: number;
  route: Route | null;
}

const PREFIX = "/s/";

/** What goes from pi to llama-server besides the body. Never pi's key. */
const FORWARDED_HEADERS = ["content-type", "accept"];

const NO_OWNER = "Esta Sesión no tiene dueño, así que no puede llegar a un modelo.";
const NO_MODEL = "No hay un Local model activo para el chat: un admin tiene que elegir uno.";
const MODEL_CHANGED = "wrong_model: el Local model de la Instance cambió; el turno sigue en el modelo nuevo.";

/**
 * Prefill progress from llama-server's SSE: with `return_progress` the stream carries a
 * `prompt_progress` object every batch. Anything unparseable is skipped: this is an observer, and a
 * frame split across two packets is followed by one with the same running total.
 */
function readProgress(text: string, report: (prefill: Prefill) => void): void {
  for (const line of text.split("\n")) {
    if (!line.startsWith("data:")) continue;
    const body = line.slice(5).trim();
    if (!body.includes("prompt_progress")) continue;
    try {
      const p = (JSON.parse(body) as { prompt_progress?: Record<string, number> }).prompt_progress;
      if (!p || typeof p.total !== "number") continue;
      report({ total: p.total, cache: p.cache ?? 0, processed: p.processed ?? 0, timeMs: p.time_ms ?? 0 });
    } catch {
      // A split frame; the next one carries the same total.
    }
  }
}

/** An error pi shows: OpenAI's SDK reads the text from `error.message`. */
function fail(res: http.ServerResponse, status: number, message: string): void {
  if (res.headersSent) return void res.end();
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify({ error: { type: "rinthel_error", message }, detail: message }));
}

/** Ask llama-server for progress on a streaming completion, leaving anything else alone. */
function withProgress(body: Buffer): Buffer {
  try {
    const parsed = JSON.parse(body.toString("utf8"));
    if (!parsed || typeof parsed !== "object" || parsed.stream !== true) return body;
    parsed.return_progress = true;
    return Buffer.from(JSON.stringify(parsed));
  } catch {
    return body;
  }
}

/** llama-server's headers as pi gets them: `fetch` already decoded the body, so these three describe bytes pi never sees. */
function relayedHeaders(upstream: Response): Record<string, string> {
  const headers: Record<string, string> = {};
  upstream.headers.forEach((value, name) => {
    if (!["content-encoding", "content-length", "transfer-encoding"].includes(name)) headers[name] = value;
  });
  return headers;
}

export class SessionProxy {
  private server?: http.Server;
  private origin = "";
  private byToken = new Map<string, Session>();
  private tokenOf = new Map<string, string>();

  constructor(
    private readonly deps: {
      routing: ModelRouting;
      slots: SessionSlots;
      onProgress: (sessionId: string, prefill: Prefill) => void;
      /** Every time the Session's route is read anew: at open, and each time a call finds it moved. */
      onRoute: (sessionId: string, route: Route | null) => void;
    },
  ) {}

  /** Listens on loopback: this exists for the pi in this process, nobody else. */
  async start(): Promise<void> {
    if (this.server) return;
    const server = http.createServer((req, res) => void this.handle(req, res));
    this.server = server;
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    this.origin = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    server.unref();
  }

  stop(): void {
    this.server?.closeAllConnections();
    this.server?.close();
    this.server = undefined;
  }

  /** Reads the route and gives the Session its own unguessable URL. A Session with no owner is refused here, before pi starts. */
  async open(sessionId: string, ownerUserId: number | null): Promise<ModelAccess> {
    this.close(sessionId);
    if (ownerUserId === null) throw new Error(NO_OWNER);
    const session: Session = { sessionId, ownerUserId, route: await this.deps.routing.read("llm") };
    this.deps.onRoute(sessionId, session.route);
    const token = randomBytes(32).toString("base64url");
    this.byToken.set(token, session);
    this.tokenOf.set(sessionId, token);
    return { url: `${this.origin}${PREFIX}${token}`, route: () => session.route };
  }

  close(sessionId: string): void {
    const token = this.tokenOf.get(sessionId);
    if (token) this.byToken.delete(token);
    this.tokenOf.delete(sessionId);
  }

  private async handle(req: http.IncomingMessage, res: http.ServerResponse): Promise<void> {
    const url = req.url ?? "";
    const rest = url.startsWith(PREFIX) ? url.slice(PREFIX.length) : "";
    const slash = rest.indexOf("/");
    const session = this.byToken.get(slash === -1 ? rest : rest.slice(0, slash));
    if (!session) return void res.writeHead(404).end();

    let route: Route | null;
    try {
      route = await this.deps.routing.read("llm");
    } catch (e) {
      return fail(res, 502, `routing: ${(e as Error).message}`);
    }
    if (route?.model !== session.route?.model || route?.url !== session.route?.url) {
      const moved = session.route !== null;
      session.route = route;
      this.deps.onRoute(session.sessionId, route);
      if (route && moved) return fail(res, 409, MODEL_CHANGED);
    }
    if (!route) return fail(res, 503, NO_MODEL);

    const chunks: Buffer[] = [];
    for await (const c of req) chunks.push(c as Buffer);
    const raw = Buffer.concat(chunks);
    const body = raw.length ? withProgress(raw) : raw;
    const headers: Record<string, string> = {};
    for (const name of FORWARDED_HEADERS) {
      const value = req.headers[name];
      if (typeof value === "string") headers[name] = value;
    }

    const controller = new AbortController();
    res.on("close", () => controller.abort());
    // Only a call that runs the model uses the slot; a read (`GET /v1/models`) goes straight through.
    const turn: SlotTurn | null = req.method === "POST"
      ? await this.deps.slots.begin({ llama: route.url, name: slotName(session.ownerUserId, route.model, session.sessionId) })
      : null;
    let completed = false;
    try {
      if (controller.signal.aborted) return;
      let upstream: Response;
      try {
        upstream = await fetch(route.url + (slash === -1 ? "" : rest.slice(slash)), {
          method: req.method,
          headers,
          body: body.length ? new Uint8Array(body) : undefined,
          signal: controller.signal,
        });
      } catch (error) {
        if (!res.destroyed) fail(res, 502, `llama-server: ${(error as Error).message}`);
        return;
      }
      res.writeHead(upstream.status, relayedHeaders(upstream));
      const streaming = (upstream.headers.get("content-type") ?? "").includes("event-stream");
      let pending = "";
      for await (const c of upstream.body ?? []) {
        if (streaming) {
          pending += Buffer.from(c).toString("utf8");
          const end = pending.lastIndexOf("\n");
          if (end >= 0) {
            readProgress(pending.slice(0, end), (prefill) => this.deps.onProgress(session.sessionId, prefill));
            pending = pending.slice(end + 1);
          }
        }
        res.write(c);
      }
      res.end();
      // A call cut short, or one llama-server refused, does not hold a whole turn: nothing to save.
      completed = upstream.status < 400 && !controller.signal.aborted;
    } catch {
      if (!res.destroyed) res.end();
    } finally {
      await turn?.end(completed);
    }
  }
}
