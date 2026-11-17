import type { CdpProbe } from "../instance-browser.js";

/** How long one CDP read may take: a browser that does not answer in that time is not running. */
const CDP_TIMEOUT_MS = 4000;

/** `CdpProbe` over the browser's DevTools HTTP endpoints (`/json/version`, `/json/list`) at `cdpUrl`. */
export function cdpOverHttp(cdpUrl: string, timeoutMs = CDP_TIMEOUT_MS): CdpProbe {
  const read = async <T>(path: string): Promise<T | null> => {
    try {
      const response = await fetch(`${cdpUrl}${path}`, { signal: AbortSignal.timeout(timeoutMs) });
      return response.ok ? ((await response.json()) as T) : null;
    } catch {
      // Not running is a normal state, not an error: the browser is optional.
      return null;
    }
  };
  return {
    async version() {
      const body = await read<{ Browser?: unknown }>("/json/version");
      return typeof body?.Browser === "string" ? body.Browser : null;
    },
    async pages() {
      const targets = await read<{ type: string; title: string; url: string }[]>("/json/list");
      return Array.isArray(targets) ? targets.filter((t) => t.type === "page").map((t) => ({ title: t.title, url: t.url })) : [];
    },
  };
}
