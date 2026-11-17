import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { adminGate, serviceUrl, tokenRefused, type AdminToolAccess } from "../admin-tool.js";
import { textResult, toolLabel } from "../tool-text.js";

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

// The names live with the other admin-only tools, where the Guard reads them too.
export { HOST_EXEC_TOOLS } from "../admin-tool.js";

/** How Deck reaches hostexecd: what the daemon hands it by environment. */
export interface HostExecAccess {
  url: string;
  token: string;
}

export interface HostExecOptions extends HostExecAccess, AdminToolAccess {}

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

/** An ExtensionFactory (pi's inline extension), one instance per admin Session. */
export function hostExecExtension({ url, token, adminNow }: HostExecOptions) {
  // Only an http(s) URL can be hostexecd: anything else fails the registration.
  const base = serviceUrl(url, "hostexecd URL").href.replace(/\/+$/, "");
  const requireAdmin = adminGate(adminNow, "host exec is");

  async function request(path: string, init: RequestInit = {}): Promise<any> {
    let res: Response;
    try {
      res = await fetch(`${base}${path}`, { ...init, headers: { ...(init.headers ?? {}), [TOKEN_HEADER]: token } });
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      throw new Error(`Could not reach hostexecd at ${base} (${detail}). The daemon runs it with BOOT; tell the admin instead of retrying.`);
    }
    if (res.status === 401) throw tokenRefused("hostexecd", "RINTHEL_HOSTEXECD_TOKEN");
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`hostexecd answered ${res.status}: ${body || "(empty)"}`);
    }
    return res.json();
  }

  return (pi: ExtensionAPI): void => {
    pi.registerTool({
      name: "rinthel_host_exec",
      label: toolLabel("rinthel_host_exec"),
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
      label: toolLabel("rinthel_host_exec_history"),
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
