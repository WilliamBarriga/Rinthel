import type { SettingsRepo } from "./store/port.js";

/** The Instance browser's login (its VNC page) and ports, as saved by the admin. */
export interface BrowserConfig {
  user: string;
  password: string;
  port: string;
  httpsPort: string;
}

/** What the Instance browser keeps in Deck's settings: its saved config and the allowlist. */
export interface BrowserSettings {
  config(): Promise<BrowserConfig>;
  /** Saves the non-empty fields of `patch` and answers the config as it now is. */
  save(patch: Partial<BrowserConfig>): Promise<BrowserConfig>;
  /**
   * Domains the browser may be pointed at, as globs. Empty means no restriction: the per-Session
   * toggle is the gate, and a list nobody filled in should not quietly block everything.
   */
  allowlist(): Promise<string[]>;
  setAllowlist(domains: string): Promise<void>;
}

const KEYS: Record<keyof BrowserConfig, string> = {
  user: "browser_user",
  password: "browser_password",
  port: "browser_port",
  httpsPort: "browser_https_port",
};

/** The browser's settings over Deck's key/value settings; `defaults` is what the environment says. */
export function browserSettings(settings: SettingsRepo, defaults: Partial<BrowserConfig> = {}): BrowserSettings {
  const config = async (): Promise<BrowserConfig> => {
    const s = await settings.all();
    return {
      user: s[KEYS.user] || defaults.user || "agent",
      password: s[KEYS.password] || defaults.password || "",
      port: s[KEYS.port] || defaults.port || "3010",
      httpsPort: s[KEYS.httpsPort] || defaults.httpsPort || "3011",
    };
  };
  return {
    config,
    async save(patch) {
      for (const [k, v] of Object.entries(patch)) {
        if (k in KEYS && typeof v === "string" && v) await settings.set(KEYS[k as keyof BrowserConfig], v);
      }
      return config();
    },
    async allowlist() {
      const raw = (await settings.all()).browser_allowlist ?? "";
      return raw.split(/[\n,]/).map((d) => d.trim()).filter(Boolean);
    },
    async setAllowlist(domains) {
      await settings.set("browser_allowlist", domains.trim());
    },
  };
}
