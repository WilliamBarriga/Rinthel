/**
 * The Deck server for the browser specs: the real `createDeckApp` (every router, in its real order)
 * over the in-memory store and the fake daemon of the server tests, with no pi, no model and no
 * secret to set.
 *
 * Real: login and the Panel token, users, Sessions and their events, Canvases and their actions,
 * Appearance, the Instance SOUL (a file in a temp root), workspaces (in memory) and the Local model
 * routes, and the Instance browser's admin routes (over an in-memory runtime and a fake CDP endpoint;
 * its `/browser-ui` view answers 502, and a spec routes the frame itself). Doubled, because they need
 * pi: the Sessions' runtime. `ScriptedSessions` answers a prompt
 * the way the Agent would, writing events and a `ui` Canvas through the real store and Canvases.
 */
import { EventEmitter } from "node:events";
import { randomUUID } from "node:crypto";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { FakeDaemon } from "../../helpers/fake-daemon.mts";
import { DEMO_USER, MODELS, NOTE_REPLY, REPLY } from "./scenario.mts";
import type { DeckSessions } from "../../../server/src/app.ts";
import type { PortalStore } from "../../../server/src/store/port.ts";
import type { Canvases } from "../../../server/src/canvases.ts";

export const PANEL_SECRET = "browser-spec-panel-secret";

/** What the Agent "writes" in `canvas_write`: a `ui` Canvas whose one button leaves a note for the Agent. */
const SPEC = {
  root: "page",
  state: { q: "" },
  elements: {
    page: { type: "Stack", props: {}, children: ["title", "ask"] },
    title: { type: "Text", props: { content: "Tablero de prueba" }, children: [] },
    ask: { type: "Button", props: { label: "Preguntar al agente" }, on: { press: { action: "askAgent", params: { message: "Explica la cláusula de exclusiones." } } }, children: [] },
  },
};

/** The Sessions' runtime without pi: a prompt is answered by a script over the real store and Canvases. */
class ScriptedSessions extends EventEmitter {
  constructor(private store: PortalStore, private canvases: Canvases) { super(); this.setMaxListeners(0); }
  isRunning = (_id: string) => false;
  anyGenerating = () => false;
  liveSnapshot = () => [];
  stop = async () => {};
  abort = async () => {};
  respondUi = () => false;

  private async record(id: string, type: string, payload: unknown) {
    this.emit(`session:${id}`, await this.store.sessions.appendEvent(id, type, payload));
  }

  async prompt(id: string, message: string) {
    void this.turn(id, message).catch((e) => console.error("[fake-deck] the scripted turn failed:", e));
    return { queued: false, turnId: randomUUID() };
  }

  private async turn(id: string, message: string) {
    await this.record(id, "portal_prompt", { message });
    await this.record(id, "portal_status", { status: "running" });
    const notes = await this.store.sessions.takeNotes(id);
    let text = REPLY;
    if (notes.length) text = `${NOTE_REPLY} ${notes.join(" ")}`;
    else if ((await this.canvases.listCanvases(id)).length === 0) {
      const canvas = await this.canvases.createCanvas(id, "Tablero", "ui");
      await this.canvases.writeCanvasSpec(id, canvas.id, canvas.revision, SPEC);
    }
    await this.record(id, "message_end", { message: { role: "assistant", content: [{ type: "text", text }] } });
    await this.record(id, "portal_status", { status: "idle" });
    await this.record(id, "agent_settled", {});
  }
}

export async function buildFakeDeck() {
  // `identity.ts` reads the secret when it is imported, so it is set first and the server code is loaded after.
  process.env.RINTHEL_PANEL_SECRET = PANEL_SECRET;
  const { createMemoryStore } = await import("../../../server/src/store/memory/index.ts");
  const { createDeckApp } = await import("../../../server/src/app.ts");
  const { daemonSessionIdentity } = await import("../../../server/src/daemon-session-identity.ts");
  const { createCanvases } = await import("../../../server/src/canvases.ts");
  const { createCanvasActions, storedSessionNotes } = await import("../../../server/src/canvas-actions.ts");
  const { FsInstanceSoul } = await import("../../../server/src/instance-soul-fs.ts");
  const { InMemorySessionRoots } = await import("../../../server/src/session-roots.ts");
  const { InMemoryModelRouting } = await import("../../../server/src/model-routing/model-routing.ts");
  const { browserSettings } = await import("../../../server/src/browser-settings.ts");
  const { InMemoryBrowserRuntime } = await import("../../../server/src/instance-browser.ts");
  // @ts-expect-error: a plain-JS double shared with the server's own tests.
  const { fakeCdp } = await import("../../../server/test/helpers/fake-cdp.mjs");

  const daemon = new FakeDaemon(PANEL_SECRET);
  daemon.addUser(DEMO_USER.username, DEMO_USER.password, "admin");
  daemon.models = MODELS;
  daemon.activeModel = MODELS[0].id;
  const store = createMemoryStore();
  const canvases = createCanvases(store);
  const root = mkdtempSync(path.join(tmpdir(), "fake-deck-"));
  const soulFile = path.join(root, "instance", "SOUL.md");
  mkdirSync(path.dirname(soulFile), { recursive: true });
  writeFileSync(soulFile, "# SOUL.md - de prueba\n");
  const routing = new InMemoryModelRouting();
  routing.set("llm", { url: "http://127.0.0.1:1", model: MODELS[0].id, contextWindow: MODELS[0].context_window, reasoningFormat: "qwen-chat-template" });

  const app = createDeckApp({
    store,
    daemon,
    identity: daemonSessionIdentity(daemon),
    serviceSecret: "",
    sessions: new ScriptedSessions(store, canvases) as unknown as DeckSessions,
    roots: new InMemorySessionRoots(),
    slots: { forget: async () => {} },
    routing,
    canvases,
    canvasActions: createCanvasActions({ canvases, notes: storedSessionNotes(store) }),
    instanceSoul: new FsInstanceSoul(soulFile),
    webDist: path.join(root, "no-web"),
    // Installed and running, with its password: what an admin finds once it was set up.
    browser: {
      settings: browserSettings(store.settings, { password: "browser-spec-password", httpsPort: "1" }),
      runtime: new InMemoryBrowserRuntime({ container: "running" }),
      cdpUrl: (await fakeCdp()).url,
      uiHost: "127.0.0.1",
    },
  });
  return { app, daemon, store };
}
