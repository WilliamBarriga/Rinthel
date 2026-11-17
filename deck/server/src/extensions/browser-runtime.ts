import type { BrowserConfig } from "../browser-settings.js";
import { EXTERNAL_REFUSAL, PASSWORD_REFUSAL, type BrowserInstall, type BrowserRuntime } from "../instance-browser.js";
import type { DockerApi } from "./docker.js";
import type { LocalChrome } from "./browser-local.js";

/**
 * The Instance browser as something Deck installs rather than something every deployment carries: it
 * is not a service in the compose file, so nothing exists until an admin asks, and removing it leaves
 * no trace but the profile.
 */
export const IMAGE = "lscr.io/linuxserver/chromium:latest";
export const CONTAINER = "deck-browser";

export interface BrowserRuntimeOptions {
  /** `BROWSER_EXTERNAL=true`: a browser started and stopped outside Deck, only found over CDP. */
  external: boolean;
  /** The Instance browser's CDP endpoint (`BROWSER_CDP_URL`). */
  cdpUrl: string;
  docker: DockerApi;
  local: LocalChrome;
  /** The profile volume: the logins. */
  volume: string;
  timezone?: string;
}

/**
 * The container as validated by hand. `seccomp=unconfined` is Chromium's own sandbox needing room
 * (the alternative, `--no-sandbox`, is worse). Host networking puts the debugging port on the same
 * loopback as Deck without publishing it anywhere.
 */
function containerSpec(cfg: BrowserConfig, volume: string, timezone: string) {
  return {
    Image: IMAGE,
    Env: [
      "PUID=0",
      "PGID=0",
      `TZ=${timezone}`,
      `CUSTOM_USER=${cfg.user}`,
      `PASSWORD=${cfg.password}`,
      `CUSTOM_PORT=${cfg.port}`,
      `CUSTOM_HTTPS_PORT=${cfg.httpsPort}`,
      "CHROME_CLI=--remote-debugging-port=9222",
      // The image restarts the app when it exits; without this, closing the window leaves a healthy
      // container with no browser in it.
      "RESTART_APP=true",
    ],
    HostConfig: {
      NetworkMode: "host",
      SecurityOpt: ["seccomp=unconfined"],
      ShmSize: 1024 * 1024 * 1024,
      RestartPolicy: { Name: "unless-stopped" },
      Binds: [`${volume}:/config`],
    },
  };
}

const failed = (what: string, res: { status: number; body: unknown }) =>
  new Error((res.body as { message?: string } | null)?.message || `${what} failed (${res.status})`);

/**
 * The three modes behind one `BrowserRuntime`: `external` when configured so; else docker where the
 * socket is (a real headful browser whatever the host looks like); else the local Chrome.
 */
export function createBrowserRuntime(opts: BrowserRuntimeOptions): BrowserRuntime {
  const { docker, local, volume } = opts;
  let pulling: BrowserInstall["pulling"] = { active: false, line: "" };
  const external = () => {
    if (opts.external) throw new Error(EXTERNAL_REFUSAL);
  };

  const containerState = async () => {
    const { status, body } = await docker.request<{ State?: { Running?: boolean } }>("GET", `/containers/${CONTAINER}/json`);
    if (status !== 200) return { exists: false, running: false };
    return { exists: true, running: Boolean(body?.State?.Running) };
  };

  const remove = async () => {
    external();
    if (!docker.available()) return local.stop();
    await docker.request("POST", `/containers/${CONTAINER}/stop?t=10`).catch(() => {});
    const res = await docker.request("DELETE", `/containers/${CONTAINER}?force=true`);
    if (res.status >= 400 && res.status !== 404) throw failed("Remove", res);
  };

  const start = async () => {
    external();
    if (!docker.available()) return local.start();
    const res = await docker.request("POST", `/containers/${CONTAINER}/start`);
    // 304 is "already running", which is the state being asked for.
    if (res.status >= 400 && res.status !== 304) throw failed("Start", res);
  };

  return {
    async status() {
      if (opts.external) {
        let running = false;
        try {
          const response = await fetch(`${opts.cdpUrl}/json/version`, { signal: AbortSignal.timeout(4000) });
          running = response.ok && typeof ((await response.json()) as { Browser?: string }).Browser === "string";
        } catch {
          // An external browser can be stopped independently: not running is a normal answer.
        }
        return { available: false, mode: "external", image: true, container: running ? "running" : "stopped", pulling };
      }
      if (!docker.available()) {
        const l = local.status();
        return {
          available: l.available,
          mode: "local",
          image: l.available,
          container: l.running ? "running" : l.available ? "stopped" : "unavailable",
          binary: l.binary,
          headless: l.headless,
          pulling,
        };
      }
      const [image, state] = await Promise.all([docker.imagePresent(IMAGE), containerState()]);
      return { available: true, mode: "docker", image, container: !state.exists ? "absent" : state.running ? "running" : "stopped", pulling };
    },

    async install(cfg) {
      external();
      // Without Docker there is nothing to install: the local runner uses a browser already there.
      if (!docker.available()) return local.start();
      // Refused rather than defaulted: an unauthenticated browser holding live logins is the one outcome worth failing over.
      if (!cfg.password) throw new Error(PASSWORD_REFUSAL);
      if (!(await docker.imagePresent(IMAGE))) {
        pulling = { active: true, line: "starting" };
        try {
          await docker.pullImage(IMAGE, (line) => (pulling = { active: true, line }));
          pulling = { active: false, line: "done" };
        } catch (e) {
          pulling = { active: false, line: "", error: (e as Error).message };
          throw e;
        }
      }
      await docker.request("POST", "/volumes/create", { Name: volume });
      if ((await containerState()).exists) await remove();
      const created = await docker.request("POST", `/containers/create?name=${CONTAINER}`, containerSpec(cfg, volume, opts.timezone ?? "Etc/UTC"));
      if (created.status >= 400) throw failed("Create", created);
      await start();
    },

    start,

    async stop() {
      external();
      if (!docker.available()) return local.stop();
      const res = await docker.request("POST", `/containers/${CONTAINER}/stop?t=10`);
      if (res.status >= 400 && res.status !== 304) throw failed("Stop", res);
    },

    remove,

    /** Forgets the logins as well. Separate on purpose, and not undoable. */
    async forgetProfile() {
      external();
      await remove();
      if (!docker.available()) return;
      const res = await docker.request("DELETE", `/volumes/${volume}`);
      if (res.status >= 400 && res.status !== 404) throw failed("Removing the profile", res);
    },
  };
}
