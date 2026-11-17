import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

/**
 * Host exec: an admin's Agent runs shell commands on the real host, outside Deck's container, through
 * `hostexecd`, a small process the daemon runs on the host loopback (Linux only). See
 * `docs/07-host-exec.md`.
 *
 * - No allowlist: the same freedom as `bash`, but on the host, as the user that runs hostexecd and
 *   without sudo. Anything that needs root fails on its own.
 * - Blocking: `POST /exec` waits for the command (with a timeout) and answers its output at once.
 * - Admin only, checked twice: the factory is loaded only in a Session of an admin (`ToolProfile`),
 *   and every call asks again whether the owner is an admin now; no answer is a no.
 * - A tainted Session loses both tools whatever the input (`TAINT_REVOKED_TOOLS` in `guard.ts`).
 *
 * The daemon hands Deck the URL (built with `deck.host_address`) and the token. Without a token the
 * factory is never loaded; with one, a URL that cannot be hostexecd fails the registration, and the
 * Session with it.
 */

/** The tools this factory registers; the Guard revokes both from a tainted Session. */
export const HOST_EXEC_TOOLS: readonly string[] = ["rinthel_host_exec", "rinthel_host_exec_history"];

/** How Deck reaches hostexecd: what the daemon hands it by environment. */
export interface HostExecAccess {
  url: string;
  token: string;
}

export interface HostExecOptions extends HostExecAccess {
  /** Whether the Session's owner is an admin right now: asked before every call. */
  adminNow: () => Promise<boolean>;
}

const TOKEN_HEADER = "X-Rinthel-Token";

interface ExecResponse {
  exit_code: number;
  stdout: string;
  stderr: string;
  duration_ms: number;
  timed_out: boolean;
}

interface HistoryEntry {
  ts: number;
  command: string;
  cwd: string | null;
  exit_code: number;
  duration_ms: number;
  stdout_len: number;
  stderr_len: number;
  timed_out: boolean;
}

/** hostexecd's base URL, or a throw: only an http(s) URL can be it. */
function baseUrl(raw: string): string {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(`hostexecd URL is not valid: "${raw}"`);
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error(`hostexecd URL must be http(s): "${raw}"`);
  return url.href.replace(/\/+$/, "");
}

const textResult = (text: string, details: Record<string, unknown> = {}) => ({ content: [{ type: "text" as const, text }], details });

/** An ExtensionFactory (pi's inline extension), one instance per admin Session. */
export function hostExecExtension({ url, token, adminNow }: HostExecOptions) {
  const base = baseUrl(url);

  /** Fails closed: a member now, a gone owner or an identity that does not answer all refuse. */
  async function requireAdmin(): Promise<void> {
    let admin = false;
    try {
      admin = await adminNow();
    } catch {
      admin = false;
    }
    if (!admin) throw new Error("Refused: host exec is for an admin, and the owner of this Session is not one now (or that could not be checked).");
  }

  async function request(path: string, init: RequestInit = {}): Promise<any> {
    let res: Response;
    try {
      res = await fetch(`${base}${path}`, { ...init, headers: { ...(init.headers ?? {}), [TOKEN_HEADER]: token } });
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      throw new Error(`Could not reach hostexecd at ${base} (${detail}). The daemon runs it with BOOT; tell the admin instead of retrying.`);
    }
    if (res.status === 401) throw new Error("hostexecd refused the token (401): Deck and hostexecd do not share it. Needs the admin, not a retry.");
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`hostexecd answered ${res.status}: ${body || "(empty)"}`);
    }
    return res.json();
  }

  return (pi: ExtensionAPI): void => {
    pi.registerTool({
      name: "rinthel_host_exec",
      label: "Host exec",
      description:
        "Run a shell command on the real host machine (outside Deck's container), as the user that runs " +
        "hostexecd, without sudo. Blocking: waits for the command to finish (with a timeout) and returns " +
        "stdout, stderr and the exit code. No command allowlist: the same freedom as bash, but on the host. " +
        "Anything that needs root fails on its own. Not available once this Session has read untrusted content.",
      parameters: Type.Object({
        command: Type.String({ description: "The shell command to run on the host" }),
        cwd: Type.Optional(Type.String({ description: "Working directory on the host (default: the host user's $HOME)" })),
        timeout: Type.Optional(Type.Integer({ description: "Timeout in seconds, 1 to 600 (default: hostexecd's, 60s)" })),
      }),
      execute: async (_toolCallId: string, params: any) => {
        await requireAdmin();
        const data = (await request("/exec", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ command: params.command, cwd: params.cwd ?? null, timeout: params.timeout ?? null }),
        })) as ExecResponse;
        const header = data.timed_out
          ? `timed out after ${data.duration_ms}ms (exit ${data.exit_code})`
          : `exit ${data.exit_code} (${data.duration_ms}ms)`;
        const parts = [header];
        if (data.stdout) parts.push(`stdout:\n${data.stdout}`);
        if (data.stderr) parts.push(`stderr:\n${data.stderr}`);
        return textResult(parts.join("\n\n"), { exit_code: data.exit_code, timed_out: data.timed_out });
      },
    });

    pi.registerTool({
      name: "rinthel_host_exec_history",
      label: "Host exec history",
      description:
        "The latest rinthel_host_exec runs, as hostexecd audited them: command, exit code, duration and time, " +
        "most recent first.",
      parameters: Type.Object({
        limit: Type.Optional(Type.Integer({ description: "How many entries, most recent first, 1 to 200 (default: 20)" })),
      }),
      execute: async (_toolCallId: string, params: any) => {
        await requireAdmin();
        const limit = params.limit ?? 20;
        const data = (await request(`/history?limit=${encodeURIComponent(String(limit))}`)) as { entries: HistoryEntry[] };
        if (!data.entries.length) return textResult("No runs recorded yet.");
        return textResult(
          data.entries
            .map((e) => `[${new Date(e.ts * 1000).toISOString()}] exit ${e.exit_code}${e.timed_out ? " TIMEOUT" : ""} (${e.duration_ms}ms): ${e.command}`)
            .join("\n"),
        );
      },
    });
  };
}
