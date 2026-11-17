import type { BrowserConfig } from "./browser-settings.js";

/**
 * Which way this Instance runs its browser:
 * - `docker`: the `deck-browser` container, installed from Deck (Docker socket present);
 * - `local`: a Chrome or Chromium already on the machine (no Docker socket);
 * - `external`: one started and stopped outside Deck (`BROWSER_EXTERNAL=true`); Deck only finds it.
 */
export type BrowserMode = "docker" | "local" | "external";

export type BrowserContainer = "absent" | "stopped" | "running" | "unavailable";

/** Whether a browser can run here and whether it is up. */
export interface BrowserInstall {
  available: boolean;
  mode: BrowserMode;
  image: boolean;
  container: BrowserContainer;
  binary?: string | null;
  headless?: boolean;
  /** Progress of an image pull in flight, so a multi-gigabyte download is not silence. */
  pulling: { active: boolean; line: string; error?: string };
}

/**
 * Port: the Instance browser's own lifecycle. The admin installs, starts and stops it by hand; nothing
 * stops it for being idle, so its logins stay alive. `install` refuses a docker install with no
 * password (an unauthenticated browser holding live logins); `remove` keeps the profile (the logins),
 * `forgetProfile` drops it too. An `external` browser is only found: every write is refused.
 */
export interface BrowserRuntime {
  status(): Promise<BrowserInstall>;
  install(config: BrowserConfig): Promise<void>;
  start(): Promise<void>;
  stop(): Promise<void>;
  remove(): Promise<void>;
  forgetProfile(): Promise<void>;
}

/**
 * Port: what the Instance browser says over its fixed CDP endpoint. Not running is a normal answer,
 * never a throw: `version` is `null` and `pages` is empty.
 */
export interface CdpProbe {
  /** The browser's product string (`Chrome/…`), or `null` when nothing answers as a browser there. */
  version(): Promise<string | null>;
  /** The open pages (tabs), or none when it cannot be read. */
  pages(): Promise<{ title: string; url: string }[]>;
}

export const EXTERNAL_REFUSAL = "This browser is managed outside Deck";
export const PASSWORD_REFUSAL = "Set a password before installing: it guards a browser holding live logins";

/** The scriptable double: the docker mode's rules, in memory. `log` lists each write that went through. */
export class InMemoryBrowserRuntime implements BrowserRuntime {
  readonly log: string[] = [];
  private container: BrowserContainer;
  private profile = false;

  constructor(private readonly opts: { available?: boolean; container?: BrowserContainer } = {}) {
    this.container = opts.available === false ? "unavailable" : (opts.container ?? "absent");
  }

  private installed(): boolean {
    return this.container === "running" || this.container === "stopped";
  }

  async status(): Promise<BrowserInstall> {
    return { available: this.opts.available !== false, mode: "docker", image: this.installed(), container: this.container, pulling: { active: false, line: "" } };
  }

  async install(config: BrowserConfig): Promise<void> {
    if (this.opts.available === false) throw new Error("No browser can run here");
    if (!config.password) throw new Error(PASSWORD_REFUSAL);
    this.log.push("install");
    this.profile = true;
    this.container = "running";
  }

  async start(): Promise<void> {
    if (!this.installed()) throw new Error("Start failed (404)");
    this.log.push("start");
    this.container = "running";
  }

  async stop(): Promise<void> {
    if (!this.installed()) throw new Error("Stop failed (404)");
    this.log.push("stop");
    this.container = "stopped";
  }

  async remove(): Promise<void> {
    this.log.push("remove");
    if (this.opts.available !== false) this.container = "absent";
  }

  async forgetProfile(): Promise<void> {
    await this.remove();
    this.log.push("forget");
    this.profile = false;
  }

  /** Whether the profile (the logins) is still kept. */
  get hasProfile(): boolean {
    return this.profile;
  }
}
