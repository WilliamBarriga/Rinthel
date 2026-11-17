import { EventEmitter } from "node:events";
import { randomUUID } from "node:crypto";
import type { PiClient } from "./pi/types.js";
import type { SdkLaunch } from "./pi/sdk-client.js";
import type { ModelAccess, Prefill } from "./session-proxy.js";
import type { Route } from "./model-routing/model-routing.js";
import type { PortalStore } from "./store/port.js";
import type { Canvases } from "./canvases.js";
import type { SessionIdentity } from "./session-identity.js";
import { workspaceOf, type SessionRoots } from "./session-roots.js";
import { LiveEvents } from "./live-events.js";
import { isClosed, ownerIsAdminNow, sameProfile, toolProfileFor, type ToolProfile } from "./tool-profile.js";
import type { HostExecAccess } from "./pi/host-exec/host-exec-tools.js";

/**
 * Events delivered to whoever watches and never stored: extension dialogs (a stored one would reopen
 * on every reload), prefill progress (a hundred rows per prompt) and the route (read afresh on reload).
 */
const EPHEMERAL_EVENTS = new Set(["queue_update", "extension_ui_request", "extension_ui_cancel", "portal_prefill", "portal_route"]);

/** What a Session's model is reached through (`SessionProxy`). */
export interface ModelProxy {
  open(sessionId: string, ownerUserId: number | null): Promise<ModelAccess>;
  close(sessionId: string): void;
}

export interface SessionManagerDeps {
  store: PortalStore;
  /** The owner's current role, read at each launch and each Turn: what `ToolProfile` decides by. */
  identity: SessionIdentity;
  /** Every Session's only way to a model. */
  proxy: ModelProxy;
  roots: SessionRoots;
  /** The Canvases the Agent writes in a Session; without them Sessions have no canvas tools. */
  canvases?: Canvases;
  /** Where the Instance SOUL is: a member's Session loads it as its SOUL. */
  instanceSoulFile?: string;
  /** hostexecd, when the daemon handed Deck a token: an admin's Sessions get the host exec tools. */
  hostExec?: HostExecAccess;
  /** Starts a Session's pi; the SDK in production, a double in the tests. */
  launch: (opts: SdkLaunch) => Promise<PiClient>;
}

export interface PromptOptions {
  /**
   * Said to the model before the message, never shown as what the person wrote: the staff framing of
   * the first prompt.
   */
  framing?: string;
  turnId?: string;
}

export interface PromptAccepted {
  queued: boolean;
  turnId: string;
}

/** What the owner reads when the Session's previous pi file is gone and the Session starts afresh. */
export const SESSION_FILE_GONE = "El historial anterior de esta Sesión ya no existe en el disco: la Sesión empieza de nuevo. Lo que se ve arriba es solo el registro de Deck; el modelo no lo recuerda.";

/** What the Agent reads when the person used a button of one of its `ui` Canvases: what was sent, said once. */
export function canvasNotesBlock(notes: string[]): string {
  return ["[Messages the person sent from an interface Canvas, since your last turn:]", ...notes.map((note) => `- ${note}`)].join("\n");
}

interface LiveSession {
  client: PiClient;
  profile: ToolProfile;
}

/**
 * Owns every running pi. A run is tied to this manager, not to an HTTP request: once a prompt is
 * accepted the browser can go, output keeps streaming into the event log (`session:<id>` events and
 * `deck.db`), and a later reconnect replays it.
 */
export class SessionManager extends EventEmitter {
  private live = new Map<string, LiveSession>();
  private starting = new Map<string, Promise<PiClient>>();
  private cancelledStarts = new Set<string>();
  private marking = new Map<string, Promise<void>>();
  private stream = new LiveEvents((session, type, payload) => this.deps.store.sessions.appendEvent(session, type, payload));
  /** Events are published in the order they were recorded, whatever the store's latency. */
  private recording: Promise<unknown> = Promise.resolve();

  constructor(private readonly deps: SessionManagerDeps) {
    super();
    this.setMaxListeners(0);
  }

  private get store(): PortalStore {
    return this.deps.store;
  }

  liveSnapshot(sessionId: string) {
    return this.stream.snapshot(sessionId);
  }

  isRunning(sessionId: string): boolean {
    return this.live.get(sessionId)?.client.running ?? false;
  }

  isGenerating(sessionId: string): boolean {
    return this.live.get(sessionId)?.client.isIdle() === false;
  }

  /** Whether any Session's model is working right now: a Local model switch waits for none. */
  anyGenerating(): boolean {
    return [...this.live.keys()].some((id) => this.isGenerating(id));
  }

  /** How far llama-server has got through the prompt. Straight out to the browser. */
  reportPrefill(sessionId: string, prefill: Prefill): void {
    this.record(sessionId, "portal_prefill", prefill);
  }

  /** The Local model the Session talks to now, for the composer. */
  reportRoute(sessionId: string, route: Route | null): void {
    this.record(sessionId, "portal_route", { model: route?.model ?? null, context_window: route?.contextWindow ?? null });
  }

  private record(sessionId: string, type: string, payload: unknown): void {
    this.recording = this.recording.then(() => this.recordNow(sessionId, type, payload))
      .catch((e) => console.error("[sessions] could not record an event:", e));
  }

  private async recordNow(sessionId: string, type: string, payload: unknown): Promise<void> {
    if (EPHEMERAL_EVENTS.has(type)) {
      // A negative seq: delivered to whoever is attached, never a replay cursor.
      this.emit(`session:${sessionId}`, { seq: -Date.now(), session_id: sessionId, type, payload: JSON.stringify(payload) });
      return;
    }
    const row = await this.stream.record(sessionId, type, payload);
    this.emit(`session:${sessionId}`, row);
  }

  /** Moves a Session's status and tells whoever watches, one at a time per Session. */
  private mark(sessionId: string, status: "running" | "idle"): Promise<void> {
    const run = (this.marking.get(sessionId) ?? Promise.resolve()).then(async () => {
      if ((await this.store.sessions.get(sessionId))?.status === status) return;
      await this.store.sessions.update(sessionId, status === "running" ? { status, last_error: null } : { status });
      this.record(sessionId, "portal_status", { status });
    });
    const settled = run.catch(() => undefined);
    this.marking.set(sessionId, settled);
    void settled.then(() => { if (this.marking.get(sessionId) === settled) this.marking.delete(sessionId); });
    return run;
  }

  /** Starts pi for a Session, once: two callers on a cold Session get the same launch. */
  private ensureClient(sessionId: string): Promise<PiClient> {
    const existing = this.live.get(sessionId);
    if (existing?.client.running) return Promise.resolve(existing.client);
    const starting = this.starting.get(sessionId);
    if (starting) return starting;
    const launch = this.startClient(sessionId).finally(() => {
      this.starting.delete(sessionId);
      this.cancelledStarts.delete(sessionId);
    });
    this.starting.set(sessionId, launch);
    return launch;
  }

  private async profileOf(owner: number | null): Promise<ToolProfile> {
    if (owner === null) throw new Error("Esta Sesión no tiene dueño, así que no puede iniciarse.");
    return toolProfileFor(owner, this.deps.identity);
  }

  private async startClient(sessionId: string): Promise<PiClient> {
    const session = await this.store.sessions.get(sessionId);
    if (!session) throw new Error(`Unknown session ${sessionId}`);
    // Before anything is created: an owner that is gone, or an identity that does not answer, stops the launch here.
    const profile = await this.profileOf(session.owner_user_id);
    const owner = session.owner_user_id!;
    const cwd = workspaceOf(this.deps.roots, { ...session, owner_user_id: owner }, profile.kind === "general");
    const sessionDir = this.deps.roots.sessionDir(sessionId);
    const modelAccess = await this.deps.proxy.open(sessionId, owner);
    if (this.cancelledStarts.has(sessionId)) {
      this.deps.proxy.close(sessionId);
      throw new Error("Inicio cancelado");
    }
    const previous = session.pi_session_file || undefined;
    let client: PiClient;
    try {
      client = await this.deps.launch({
        cwd,
        sessionDir,
        sessionFile: previous,
        modelAccess,
        profile,
        sessionId,
        taintMarks: this.store.sessionTaint,
        canvases: this.deps.canvases,
        instanceSoulFile: isClosed(profile) ? this.deps.instanceSoulFile : undefined,
        // Admin only: loaded for the general profile, and the role asked again on every call.
        hostExec: this.deps.hostExec && !isClosed(profile)
          ? { ...this.deps.hostExec, adminNow: () => ownerIsAdminNow(owner, this.deps.identity) }
          : undefined,
        subagents: isClosed(profile) ? undefined : { adminNow: () => ownerIsAdminNow(owner, this.deps.identity) },
        thinkingLevel: session.thinking_level || undefined,
      });
    } catch (error) {
      this.deps.proxy.close(sessionId);
      throw error;
    }
    if (this.cancelledStarts.has(sessionId)) {
      client.dispose();
      this.deps.proxy.close(sessionId);
      throw new Error("Inicio cancelado");
    }

    // pi writes its file lazily: recorded the first time it appears, and reopened from then on.
    let recordedFile: string | null = previous && client.sessionFile === previous ? previous : null;
    const historyLost = Boolean(previous) && client.sessionFile !== previous;
    if (historyLost) await this.store.sessions.update(sessionId, { pi_session_file: null });
    const rememberSessionFile = () => {
      const file = client.sessionFile;
      if (recordedFile || !file) return;
      recordedFile = file;
      void this.store.sessions.update(sessionId, { pi_session_file: file }).catch((e) => console.error("[sessions] could not record the pi file:", e));
    };

    client.on("event", (msg: any) => {
      rememberSessionFile();
      this.record(sessionId, msg.type, msg);
      // Status follows pi's own run state. agent_settled, not agent_end: retries, auto-compaction and
      // queued messages come after agent_end and are still the model working.
      if (msg.type === "agent_start") void this.mark(sessionId, "running").catch(() => {});
      if (msg.type === "agent_settled") void this.mark(sessionId, "idle").catch(() => {});
    });
    client.on("exit", async () => {
      if (this.live.get(sessionId)?.client !== client) return;
      this.forgetLive(sessionId);
      const current = await this.store.sessions.get(sessionId).catch(() => undefined);
      if (current?.status === "running") {
        const message = "pi terminó de forma inesperada";
        await this.store.sessions.update(sessionId, { status: "error", last_error: message }).catch(() => {});
        this.record(sessionId, "portal_status", { status: "error", error: message });
      }
    });
    this.live.set(sessionId, { client, profile });
    if (historyLost) this.record(sessionId, "portal_notice", { text: SESSION_FILE_GONE });
    return client;
  }

  private forgetLive(sessionId: string): void {
    this.live.delete(sessionId);
    this.stream.clear(sessionId);
    this.deps.proxy.close(sessionId);
  }

  /**
   * Before each Turn the owner's profile is read anew: a profile that moved (an admin demoted) relaunches
   * the client, aborting a run in course first, so no Turn starts with the old one.
   */
  private async syncProfile(sessionId: string, client: PiClient): Promise<PiClient> {
    const session = await this.store.sessions.get(sessionId);
    const live = this.live.get(sessionId);
    if (!session || !live || live.client !== client) return client;
    if (sameProfile(live.profile, await this.profileOf(session.owner_user_id))) return client;
    if (!client.isIdle()) {
      await client.abort().catch(() => {});
      this.record(sessionId, "portal_notice", {
        text: "El perfil de herramientas de esta Sesión cambió: el turno en curso se detuvo y lo siguiente corre con el perfil nuevo.",
        error: true,
      });
    }
    await this.stop(sessionId);
    return this.ensureClient(sessionId);
  }

  /** Submits a prompt; resolves once pi has taken it. The Session is marked running first: starting pi takes seconds. */
  async prompt(sessionId: string, message: string, options: PromptOptions = {}): Promise<PromptAccepted> {
    await this.mark(sessionId, "running");
    const turnId = options.turnId ?? randomUUID();
    try {
      const client = await this.syncProfile(sessionId, await this.ensureClient(sessionId));
      const isCommand = await this.looksLikeCommand(client, message);
      const queued = !client.isIdle();
      // What the person left through a Canvas since the last Turn reaches the Agent now, never starting one before.
      const notes = isCommand ? [] : await this.store.sessions.takeNotes(sessionId);
      if (!isCommand) this.record(sessionId, "portal_prompt", { message, turn_id: turnId });
      const framed = options.framing && !isCommand ? `${options.framing}\n\n${message}` : message;
      try {
        await client.prompt(notes.length ? `${canvasNotesBlock(notes)}\n\n${framed}` : framed);
      } catch (e) {
        for (const note of notes) await this.store.sessions.addNote(sessionId, note, false);
        throw e;
      }
      // A command that ran no agent turn leaves no agent_settled to clear the status.
      if (client.isIdle()) await this.mark(sessionId, "idle");
      return { queued, turnId };
    } catch (e) {
      const failure = (e as Error).message;
      await this.store.sessions.update(sessionId, { status: "error", last_error: failure });
      this.record(sessionId, "portal_status", { status: "error", error: failure });
      throw e;
    }
  }

  /** The live client, starting pi if needed (config reads and writes). */
  client(sessionId: string): Promise<PiClient> {
    return this.ensureClient(sessionId);
  }

  private async looksLikeCommand(client: PiClient, message: string): Promise<boolean> {
    const match = /^\/([\w:-]+)/.exec(message.trim());
    if (!match) return false;
    try {
      return (await client.getCommands()).some((c) => c.name === match[1]);
    } catch {
      return false;
    }
  }

  respondUi(sessionId: string, id: string, response: { cancelled?: boolean; value?: unknown }): boolean {
    return this.live.get(sessionId)?.client.respondUi(id, response) ?? false;
  }

  /** Compaction, marked running like a prompt: it is a model call and a minute. */
  async compact(sessionId: string): Promise<void> {
    await this.mark(sessionId, "running");
    try {
      await (await this.ensureClient(sessionId)).compact();
    } finally {
      await this.mark(sessionId, "idle");
    }
  }

  async abort(sessionId: string): Promise<void> {
    const live = this.live.get(sessionId);
    if (!live?.client.running) {
      if (this.starting.has(sessionId)) await this.stop(sessionId);
    } else {
      await live.client.abort().catch(() => {});
    }
    await this.store.sessions.update(sessionId, { status: "idle" });
    this.record(sessionId, "portal_status", { status: "idle", aborted: true });
  }

  /** Stops a Session's pi (or the launch in course) and lets its route go. */
  async stop(sessionId: string): Promise<void> {
    const starting = this.starting.get(sessionId);
    if (starting) {
      this.cancelledStarts.add(sessionId);
      await starting.catch(() => {});
    }
    const live = this.live.get(sessionId);
    if (!live) return;
    this.forgetLive(sessionId);
    live.client.dispose();
  }

  async shutdown(): Promise<void> {
    await Promise.all([...this.live.keys()].map((id) => this.stop(id)));
  }
}
