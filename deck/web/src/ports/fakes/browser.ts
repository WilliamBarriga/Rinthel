import type { BrowserStatus } from "@deck/contract";
import type { BrowserApi } from "../browser";
import { PortError } from "../http-errors";

export interface FakeBrowserApi extends BrowserApi {
  /** Makes the next call to `op` (a method name of the port) reject with `error`. */
  failNext(op: keyof BrowserApi, error: Error): void;
  /** Every write that went through, in order (`install`, `start`, `stop`, `remove`, `forget`, `config`, `allowlist`, `session:<id>:<on|off>`). */
  readonly log: string[];
  /** How many times `status` was asked. */
  readonly statusCalls: number;
}

export interface FakeBrowserSeed {
  /** Whether a browser can run here at all (default yes). */
  available?: boolean;
  mode?: BrowserStatus["install"]["mode"];
  container?: BrowserStatus["install"]["container"];
  hasPassword?: boolean;
  /** The Sessions that may drive it. */
  sessions?: BrowserStatus["sessions"];
  pages?: BrowserStatus["pages"];
  allowlist?: string;
  uiPort?: string;
  /** The reader is not an admin: every call is a `403`. */
  forbidden?: boolean;
}

const FORBIDDEN = "Solo el administrador puede usar el browser de la Instance.";

/**
 * The Instance browser as Node reports it, with the rules of its routes: installing needs a place
 * where one can run and, in docker mode, a password; start and stop need it installed; `remove`
 * leaves it `absent`. Each call reads and writes the same state, so a controller sees what its own
 * writes changed.
 */
export function fakeBrowserApi(seed: FakeBrowserSeed = {}): FakeBrowserApi {
  const available = seed.available ?? true;
  const mode = seed.mode ?? "docker";
  let container: BrowserStatus["install"]["container"] = available ? (seed.container ?? "absent") : "unavailable";
  let hasPassword = seed.hasPassword ?? false;
  let allowlist = seed.allowlist ?? "";
  const sessions = structuredClone(seed.sessions ?? []);
  const failures = new Map<keyof BrowserApi, Error>();
  const log: string[] = [];
  let statusCalls = 0;
  const check = (op: keyof BrowserApi) => {
    if (seed.forbidden) throw new PortError("http", 403, FORBIDDEN);
    const error = failures.get(op);
    if (error) {
      failures.delete(op);
      throw error;
    }
  };
  const installed = () => container === "running" || container === "stopped";
  const external = () => {
    if (mode === "external") throw new PortError("http", 400, "This browser is managed outside Deck");
  };
  return {
    log,
    get statusCalls() {
      return statusCalls;
    },
    async status() {
      statusCalls++;
      check("status");
      return {
        running: container === "running",
        unprotected: container === "running" && !hasPassword,
        sessions: structuredClone(sessions),
        config: { user: "agent", hasPassword },
        version: container === "running" ? "Chrome/130" : null,
        pages: container === "running" ? structuredClone(seed.pages ?? []) : [],
        uiPort: seed.uiPort ?? "3011",
        allowlist,
        install: { available, mode, image: installed(), container, pulling: { active: false, line: "" } },
      };
    },
    async install() {
      check("install");
      external();
      if (!available) throw new PortError("http", 400, "No Chrome or Chromium found on this machine");
      if (mode === "docker" && !hasPassword) throw new PortError("http", 400, "Set a password before installing: it guards a browser holding live logins");
      log.push("install");
      container = "running";
    },
    async start() {
      check("start");
      external();
      if (!installed()) throw new PortError("http", 400, "Start failed (404)");
      log.push("start");
      container = "running";
    },
    async stop() {
      check("stop");
      external();
      if (!installed()) throw new PortError("http", 400, "Stop failed (404)");
      log.push("stop");
      container = "stopped";
    },
    async remove(forgetProfile = false) {
      check("remove");
      external();
      log.push(forgetProfile ? "forget" : "remove");
      if (available) container = "absent";
    },
    async setConfig(patch) {
      check("setConfig");
      log.push("config");
      if (patch.password) hasPassword = true;
    },
    async suggestPassword() {
      check("suggestPassword");
      return "0123456789abcdef01234567";
    },
    async setAllowlist(domains) {
      check("setAllowlist");
      log.push("allowlist");
      allowlist = domains.split(/[\n,]/).map((d) => d.trim()).filter(Boolean).join("\n");
      return allowlist;
    },
    async setSessionBrowser(sessionId, enabled) {
      check("setSessionBrowser");
      log.push(`session:${sessionId}:${enabled ? "on" : "off"}`);
      const at = sessions.findIndex((s) => s.id === sessionId);
      if (enabled && at < 0) sessions.push({ id: sessionId, title: sessionId, kind: "agent" });
      if (!enabled && at >= 0) sessions.splice(at, 1);
      return enabled;
    },
    failNext(op, error) {
      failures.set(op, error);
    },
  };
}
