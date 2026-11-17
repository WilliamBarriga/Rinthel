import { EventEmitter } from "node:events";
import { existsSync, lstatSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import type { PiClient, PiCommand, PiState, PiStats } from "./types.js";
import { acceptPrompt } from "./accept-prompt.js";
import { guardExtension, guardReporter } from "./guard.js";
import { SessionTaint } from "./session-taint.js";
import type { SessionTaintRepo } from "../store/port.js";
import { routedModel, rinthelProviderExtension } from "./rinthel-provider.js";
import type { ModelAccess } from "../session-proxy.js";
import { isClosed, type ToolProfile } from "../tool-profile.js";
import type { Canvases } from "../canvases.js";
import { CanvasTools } from "./canvas-tools.js";
import type { BrowserDriver } from "../browser-driver.js";
import type { SessionBrowserState } from "../session-browser.js";
import { sessionBrowserTools } from "./session-browser-tools.js";
import { BROWSER_READING_RULE, BROWSER_SCREENSHOT_RULE } from "./browser-snapshot.js";

/**
 * The Agent's own files: SOUL.md is who it is, PrimaryUser.md and MEMORY.md its owner's notes. Read
 * from the Session's working directory when they are there (the Agent's home has them; a workspace
 * usually does not), never through a link.
 */
const CONTEXT_FILES = ["SOUL.md", "PrimaryUser.md", "MEMORY.md"];

export function extraContextFiles(home: string, instanceSoulFile?: string): { name: string; path: string; content: string }[] {
  const out: { name: string; path: string; content: string }[] = [];
  for (const name of CONTEXT_FILES) {
    // A member's SOUL.md is the Instance SOUL, never one in their home.
    const file = name === "SOUL.md" && instanceSoulFile !== undefined ? instanceSoulFile : path.join(home, name);
    try {
      if (!lstatSync(file).isFile()) continue;
      out.push({ name, path: file, content: readFileSync(file, "utf8") });
    } catch {
      // Absent or unreadable is the same here: the Session still starts.
    }
  }
  return out;
}

/**
 * One line saying the files are the Agent's own: handed over as plain context files, pi presents them
 * as reference material and the model answers "who are you" from its base identity instead.
 */
export function framing(home: string, instanceSoulFile?: string): string[] {
  const present = extraContextFiles(home, instanceSoulFile).map((file) => file.name);
  return present.length
    ? [`${present.join(", ")} in your context are yours, not reference material about someone else. Each opens with a block saying what it is for; follow it.`]
    : [];
}

/** Read a member that may be a getter or a method, without assuming which. */
function callable(obj: any, key: string): any {
  const v = obj?.[key];
  return typeof v === "function" ? v.call(obj) : v;
}

const asArray = (v: any): any[] => {
  const resolved = typeof v === "function" ? v() : v;
  return Array.isArray(resolved) ? resolved : [];
};

export interface SdkLaunch {
  /** Where the Session works, and where its context files are read from. */
  cwd: string;
  /** The Session's pi directory: its session files, and a closed profile's runtime. */
  sessionDir: string;
  /** A previous run's pi session file, reopened exactly when it still exists. */
  sessionFile?: string;
  /** The Session's only way to a model (`rinthel-provider.ts`). */
  modelAccess: ModelAccess;
  thinkingLevel?: string;
  /** What the Session's Agent may call. */
  profile: ToolProfile;
  /** The Deck Session id, for the Guard's log. */
  sessionId: string;
  /** Where the Session's taint mark is kept, so a relaunch starts it tainted again. */
  taintMarks: SessionTaintRepo;
  /** The Canvases the Agent writes in this Session; without them it has no canvas tools. */
  canvases?: Canvases;
  /** The Instance SOUL a member's Session loads in place of a SOUL.md of its home (set for a closed profile only). */
  instanceSoulFile?: string;
  /**
   * The Instance browser, for a Session that may have it (an admin's): the driver behind its browser
   * tools and the gate read at each call. Ignored for a closed profile.
   */
  browser?: SessionBrowserLaunch;
}

export interface SessionBrowserLaunch {
  driver: BrowserDriver;
  now: () => Promise<SessionBrowserState>;
}

/**
 * pi driven through its SDK, in this process. Every Session runs with the Guard and the Local model's
 * provider, inline (no installed package). A closed profile loads nothing of pi from disk and enables
 * only its list; it fails to start rather than run with less of it closed.
 */
export class SdkPiClient extends EventEmitter implements PiClient {
  private disposed = false;
  private pendingUi = new Map<string, (r: { cancelled?: boolean; value?: unknown }) => void>();
  private unsubscribe: () => void = () => {};
  /** This Session's taint, shared with its Guard. */
  taint!: SessionTaint;
  /** The Agent's Canvas tools for this Session: they follow its events and are closed when it stops. */
  private canvasTools?: CanvasTools;

  private constructor(private readonly session: any, readonly profile: ToolProfile) {
    super();
    this.setMaxListeners(0);
  }

  static async create(opts: SdkLaunch): Promise<SdkPiClient> {
    // Imported lazily: importing this module must not load pi.
    const pi: any = await import("@earendil-works/pi-coding-agent");
    const profile = opts.profile;
    const closed = isClosed(profile);
    const runtimeDir = path.join(opts.sessionDir, "runtime");
    if (closed) mkdirSync(runtimeDir, { recursive: true });
    // A closed profile's settings live in memory and its project is not trusted: no `.pi/` of the cwd is read.
    const closedSettings = closed ? pi.SettingsManager.inMemory({}, { projectTrusted: false }) : undefined;
    const modelRuntime = await pi.ModelRuntime.create(
      closed ? { authPath: path.join(runtimeDir, "auth.json"), modelsPath: null, refreshOnCreate: false } : {},
    );

    let liveSession: any;
    const allowedTools: Set<string> | undefined = isClosed(profile) ? new Set(profile.tools) : undefined;
    const guard = guardReporter();
    // The Instance browser's tools, filled as they register: the only browser tools the Guard lets
    // through, and an untrusted source for the taint. A closed profile never gets them.
    const browser = closed ? undefined : opts.browser;
    const ownBrowserTools = new Set<string>();
    // Tainted until the Guard rebuilds it at session_start, from the stored mark and pi's file.
    const taint = new SessionTaint(opts.sessionId, opts.taintMarks, { browserTools: ownBrowserTools });
    const factories: { name: string; factory: (pi: any) => void | Promise<void> }[] = [
      // Every Session, unconditionally: any Session can read something untrusted.
      {
        name: "guard",
        factory: guardExtension({
          sessionId: opts.sessionId,
          report: guard.report,
          allowedTools,
          taint,
          browser: browser ? { owned: ownBrowserTools, now: browser.now } : undefined,
        }),
      },
      { name: "rinthel-provider", factory: rinthelProviderExtension(opts.modelAccess, (model) => liveSession.setModel(model)) },
    ];
    const canvasTools = opts.canvases ? new CanvasTools(opts.sessionId, opts.canvases) : undefined;
    if (canvasTools) factories.push({ name: "canvases", factory: canvasTools.extension });
    if (browser) {
      factories.push({
        name: "session-browser",
        factory: sessionBrowserTools(browser.driver, browser.now, {
          owned: ownBrowserTools,
          onError: (e) => console.error(`[browser] the Instance browser's tools are unavailable: ${e.message}`),
        }),
      });
    }
    const context = {
      agentsFilesOverride: (base: { agentsFiles: any[] }) => ({
        agentsFiles: [...base.agentsFiles, ...extraContextFiles(opts.cwd, opts.instanceSoulFile).map((f) => ({ path: f.path, content: f.content }))],
      }),
      appendSystemPrompt: [...framing(opts.cwd, opts.instanceSoulFile), ...(browser ? [BROWSER_READING_RULE, BROWSER_SCREENSHOT_RULE] : [])],
    };
    const resourceLoader = new pi.DefaultResourceLoader({
      cwd: opts.cwd,
      extensionFactories: factories,
      ...context,
      ...(closed
        ? {
            // Nothing from disk: no settings file, package, extension, skill, prompt template, theme or
            // context file of the cwd or its parents, and pi's default system prompt.
            agentDir: runtimeDir,
            settingsManager: closedSettings,
            noExtensions: true,
            noSkills: true,
            noPromptTemplates: true,
            noThemes: true,
            noContextFiles: true,
            systemPromptOverride: () => undefined,
          }
        : { agentDir: pi.getAgentDir() }),
    });
    await resourceLoader.reload();
    const loadErrors = resourceLoader.getExtensions().errors;
    if (loadErrors.length) {
      // The Guard and the provider are inline: a Session never runs without them.
      const inline = loadErrors.filter((e: any) => /guard|rinthel-provider/.test(String(e?.path ?? e?.extensionPath ?? "")));
      if (closed || inline.length) throw new Error("No se pudieron cargar las extensiones de la Sesión");
      for (const e of loadErrors) console.error(`[pi] extension failed to load: ${String(e?.error ?? e)}`);
    }

    // Reopen the exact file this Session owns; `continueRecent` would be a guess.
    const sessionManager = opts.sessionFile && existsSync(opts.sessionFile)
      ? pi.SessionManager.open(opts.sessionFile, opts.sessionDir, opts.cwd)
      : pi.SessionManager.create(opts.cwd, opts.sessionDir);

    const { session } = await pi.createAgentSession({
      cwd: opts.cwd,
      sessionManager,
      ...(closed ? { agentDir: runtimeDir, settingsManager: closedSettings } : {}),
      modelRuntime,
      resourceLoader,
      // A closed profile enables its list and nothing else.
      ...(allowedTools ? { tools: [...allowedTools] } : {}),
      ...(opts.thinkingLevel ? { thinkingLevel: opts.thinkingLevel } : {}),
    });

    liveSession = session;
    const client = new SdkPiClient(session, opts.profile);
    client.taint = taint;
    client.canvasTools = canvasTools;
    // Notices wait until someone listens: an event emitted before the manager subscribes is lost.
    const onListener = (name: string | symbol) => {
      if (name !== "event") return;
      client.off("newListener", onListener);
      queueMicrotask(() => guard.attach((event) => client.emit("event", event)));
    };
    client.on("newListener", onListener);
    const unsub = session.subscribe((event: any) => { canvasTools?.observe(event); client.emit("event", event); });
    client.unsubscribe = typeof unsub === "function" ? unsub : () => {};

    try {
      // Extensions stay inert until bound; a bound uiContext is what makes their dialogs reach the browser.
      await session.bindExtensions({
        uiContext: client.buildUiContext(),
        mode: "rpc",
        commandContextActions: { waitForIdle: () => session.waitForIdle(), reload: async () => { await session.reload(); } },
        onError: (err: any) => client.emit("event", { type: "extension_error", extensionPath: err?.extensionPath, error: String(err?.error ?? err) }),
      });
      // The provider exists once extensions are bound: the route's model is applied here.
      await session.setModel(routedModel(opts.modelAccess.url, opts.modelAccess.route()));
    } catch (e) {
      client.dispose();
      throw e;
    }
    return client;
  }

  get running(): boolean {
    return !this.disposed;
  }

  get sessionFile(): string | undefined {
    const file = this.session.sessionFile;
    return file && existsSync(file) ? file : undefined;
  }

  /** pi's extension dialogs, bridged to the browser: each emits a request and waits until the UI answers. */
  private buildUiContext() {
    const ask = (payload: Record<string, unknown>, opts: any, fallback: unknown) =>
      new Promise((resolve) => {
        const id = randomUUID();
        let settled = false;
        const finish = (value: unknown) => {
          if (settled) return;
          settled = true;
          this.pendingUi.delete(id);
          resolve(value);
        };
        this.pendingUi.set(id, (r) => finish(r.cancelled ? fallback : r.value));
        // Never park forever: an unanswered dialog would wedge the Session.
        const timer = setTimeout(() => {
          this.emit("event", { type: "extension_ui_cancel", id });
          finish(fallback);
        }, typeof opts?.timeout === "number" ? opts.timeout : 300_000);
        timer.unref?.();
        opts?.signal?.addEventListener?.("abort", () => finish(fallback));
        this.emit("event", { type: "extension_ui_request", id, ...payload });
      });
    const fireAndForget = (payload: Record<string, unknown>) => this.emit("event", { type: "extension_ui_request", id: randomUUID(), ...payload });
    return {
      select: (title: string, options: string[], opts?: any) => ask({ method: "select", title, options }, opts, undefined),
      confirm: (title: string, message: string, opts?: any) => ask({ method: "confirm", title, message }, opts, false),
      input: (title: string, placeholder: string, opts?: any) => ask({ method: "input", title, placeholder }, opts, undefined),
      editor: (title: string, content: string, opts?: any) => ask({ method: "editor", title, defaultValue: content }, opts, undefined),
      notify: (message: string, type?: string) => fireAndForget({ method: "notify", message, notifyType: type }),
      setStatus: (key: string, text: string) => fireAndForget({ method: "setStatus", statusKey: key, statusText: text }),
      setWidget: () => {},
      onTerminalInput: () => () => {},
      setWorkingMessage: () => {},
      setWorkingVisible: () => {},
      setWorkingIndicator: () => {},
      setHiddenThinkingLabel: () => {},
    };
  }

  respondUi(id: string, response: { cancelled?: boolean; value?: unknown }): boolean {
    const pending = this.pendingUi.get(id);
    if (!pending) return false;
    pending(response);
    return true;
  }

  async prompt(message: string): Promise<void> {
    await acceptPrompt(
      (preflightResult) => this.session.prompt(message, { expandPromptTemplates: true, streamingBehavior: "followUp", preflightResult }),
      (error) => this.emit("event", { type: "portal_notice", text: `El turno falló: ${error instanceof Error ? error.message : error}`, error: true }),
    );
  }

  async abort(): Promise<void> {
    // Compaction runs on a controller of its own: session.abort() alone would leave it going.
    if (this.session.isCompacting) this.session.abortCompaction();
    try { await this.session.abort(); } finally { await this.canvasTools?.interrupt(); }
  }

  /** `isIdle` is a getter on pi's session, not a method. */
  isIdle(): boolean {
    return this.session.isIdle;
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    try { this.unsubscribe(); } catch { /* best effort */ }
    try { this.session.dispose?.(); } catch { /* best effort */ }
    this.canvasTools?.interrupt().catch((e) => console.error("[canvas] could not interrupt writes:", e));
    this.emit("exit", { code: 0, signal: null });
  }

  async getState(): Promise<PiState> {
    const model = this.session.model;
    return {
      model: { id: model?.id ?? "unknown", name: model?.name ?? "unknown", provider: model?.provider ?? "unknown", contextWindow: model?.contextWindow },
      thinkingLevel: this.session.thinkingLevel ?? "medium",
      autoCompactionEnabled: callable(this.session, "autoCompactionEnabled") ?? true,
      messageCount: callable(this.session, "messages")?.length,
    };
  }

  async getStats(): Promise<PiStats> {
    const stats = (await this.session.getSessionStats?.()) ?? {};
    const usage = (await this.session.getContextUsage?.()) ?? {};
    const contextWindow = usage.contextWindow ?? this.session.model?.contextWindow ?? 0;
    const used = usage.tokens ?? 0;
    return {
      tokens: stats.tokens ?? { input: 0, output: 0, total: 0 },
      contextUsage: { tokens: used, contextWindow, percent: usage.percent ?? (contextWindow ? (used / contextWindow) * 100 : 0) },
      toolCalls: stats.toolCalls ?? 0,
      totalMessages: stats.totalMessages ?? 0,
    };
  }

  async getThinkingLevels(): Promise<string[]> {
    const levels = callable(this.session, "getAvailableThinkingLevels");
    return Array.isArray(levels) && levels.length ? levels : ["off", "minimal", "low", "medium", "high", "xhigh"];
  }

  /** Extension commands, prompt templates and skills: what pi itself would offer. */
  async getCommands(): Promise<PiCommand[]> {
    const commands: PiCommand[] = [];
    for (const c of this.session.extensionRunner?.getRegisteredCommands?.() ?? []) {
      commands.push({ name: c.invocationName ?? c.name, description: c.description, source: "extension" });
    }
    for (const t of asArray(this.session.promptTemplates)) commands.push({ name: t.name, description: t.description, source: "prompt" });
    for (const skill of asArray(this.session.resourceLoader?.getSkills?.()?.skills)) {
      commands.push({ name: `skill:${skill.name}`, description: skill.description, source: "skill" });
    }
    return commands;
  }

  async setThinkingLevel(level: string): Promise<void> {
    this.session.setThinkingLevel(level);
  }

  async compact(): Promise<void> {
    await this.session.compact();
  }
}
