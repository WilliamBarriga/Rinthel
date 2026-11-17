import type { BrowserStatus } from "@deck/contract";
import { globalFetch, requestJson, type FetchLike } from "../http-errors";
import type { BrowserApi } from "../browser";

const send = (method: string, body?: unknown): RequestInit => ({ method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });

/** The `fetch` adapter only knows HTTP: URL, status and JSON body. */
export function fetchBrowserApi(fetchImpl: FetchLike = globalFetch): BrowserApi {
  const call = <T>(url: string, init?: RequestInit) => requestJson<T>(fetchImpl, url, init);
  return {
    status: () => call<BrowserStatus>("/api/browser"),
    async install() {
      await call("/api/browser/install", send("POST"));
    },
    async start() {
      await call("/api/browser/start", send("POST"));
    },
    async stop() {
      await call("/api/browser/stop", send("POST"));
    },
    async remove(forgetProfile = false) {
      await call(`/api/browser/install${forgetProfile === true ? "?profile=forget" : ""}`, send("DELETE"));
    },
    async setConfig(patch) {
      await call("/api/browser/config", send("PUT", patch));
    },
    async suggestPassword() {
      return (await call<{ password: string }>("/api/browser/suggest-password")).password;
    },
    async setAllowlist(domains) {
      return (await call<{ allowlist: string }>("/api/browser/allowlist", send("PUT", { domains }))).allowlist;
    },
    async setSessionBrowser(sessionId, enabled) {
      return (await call<{ enabled: boolean }>(`/api/sessions/${encodeURIComponent(sessionId)}/browser`, send("PUT", { enabled }))).enabled;
    },
  };
}
