import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";

/** The Chromes worth trying, `BROWSER_BINARY` first when set. */
export const CHROME_CANDIDATES = [
  "google-chrome-stable",
  "google-chrome",
  "chromium-browser",
  "chromium",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
];

export interface LocalChromeOptions {
  /** Bare names are resolved against PATH; paths are taken as they are. */
  candidates: readonly string[];
  /** The profile on Deck's volume, so the Agent's logins survive restarts as the container's do. */
  profileDir: string;
  /** The display to draw on; headless without one. */
  display?: string;
  searchPath?: string;
}

/**
 * The same browser, without a container: for an Instance with no Docker socket, where a Chrome is
 * already installed. Nothing is downloaded; if no browser is on the machine, this says so.
 */
export class LocalChrome {
  private child: ChildProcess | null = null;

  constructor(private readonly opts: LocalChromeOptions) {}

  /** The first candidate that exists, resolving bare names against PATH. */
  findBinary(): string | null {
    for (const candidate of this.opts.candidates) {
      if (candidate.includes("/")) {
        if (existsSync(candidate)) return candidate;
        continue;
      }
      for (const dir of (this.opts.searchPath ?? "").split(path.delimiter)) {
        if (!dir) continue;
        const full = path.join(dir, candidate);
        if (existsSync(full)) return full;
      }
    }
    return null;
  }

  running(): boolean {
    return Boolean(this.child && this.child.exitCode === null);
  }

  status() {
    const binary = this.findBinary();
    return {
      available: Boolean(binary),
      binary,
      running: this.running(),
      // Headful when there is a display: a headless browser is often refused by sign-in pages.
      headless: !this.opts.display,
    };
  }

  start(): void {
    if (this.running()) return;
    const binary = this.findBinary();
    if (!binary) throw new Error("No Chrome or Chromium found on this machine");
    mkdirSync(this.opts.profileDir, { recursive: true });
    const args = [
      `--user-data-dir=${this.opts.profileDir}`,
      // Bound to loopback by default, and left that way: whoever reaches the port owns every account signed in.
      "--remote-debugging-port=9222",
      "--no-first-run",
      "--no-default-browser-check",
    ];
    if (!this.opts.display) args.push("--headless=new");
    const child = spawn(binary, args, { detached: false, stdio: "ignore" });
    child.on("exit", () => {
      if (this.child === child) this.child = null;
    });
    this.child = child;
  }

  stop(): void {
    this.child?.kill("SIGTERM");
    this.child = null;
  }
}
