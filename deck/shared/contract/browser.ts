/** The Instance browser as `GET /api/browser` reports it (admin only). */
export interface BrowserStatus {
  running: boolean;
  /** Running with no password on its web UI. */
  unprotected: boolean;
  /** How and whether a browser can run here at all. */
  install: {
    available: boolean;
    mode: "docker" | "local" | "external";
    image: boolean;
    container: "absent" | "stopped" | "running" | "unavailable";
    binary?: string | null;
    headless?: boolean;
    pulling: { active: boolean; line: string; error?: string };
  };
  config: { user: string; hasPassword: boolean };
  version: string | null;
  pages: { title: string; url: string }[];
  uiPort: string;
  allowlist: string;
  /** The Sessions whose browser toggle is on. */
  sessions: { id: string; title: string; kind: string }[];
}
