import type { BrowserStatus } from "@deck/contract";

/**
 * Port: the Instance browser (`/api/browser` of Node), admin only: any other role is refused with a
 * `PortError` of status 403, and whoever reads that does not show the browser. One port for the whole
 * module: the read the chat needs (`status`), the administration of the Browser screen, and which
 * Sessions may drive it (`setSessionBrowser`), because they share audience, route family and failure
 * model. Failures reject with a `PortError` (see `http-errors.ts`).
 *
 * The live view is not a stream of this port: the browser is a VNC page Deck proxies at `/browser-ui/`
 * and a frame is its client.
 *
 * `install` is a `400` where no browser can run, or in docker mode before `setConfig` gave it a
 * password; `start` and `stop` need it installed. `remove` keeps the profile (its logins) unless
 * `forgetProfile`. `setAllowlist` takes one domain per line and answers what Deck saved; an empty text
 * means no restriction. Nothing stops the browser by itself: it runs until an admin stops it.
 */
export interface BrowserApi {
  status(): Promise<BrowserStatus>;
  install(): Promise<void>;
  start(): Promise<void>;
  stop(): Promise<void>;
  remove(forgetProfile?: boolean): Promise<void>;
  setConfig(patch: { user?: string; password?: string }): Promise<void>;
  suggestPassword(): Promise<string>;
  setAllowlist(domains: string): Promise<string>;
  /** Whether the Agent of this Session may drive the browser (only an admin's Session ever does). */
  setSessionBrowser(sessionId: string, enabled: boolean): Promise<boolean>;
}
