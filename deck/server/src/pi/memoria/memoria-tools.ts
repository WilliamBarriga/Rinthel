import http from "node:http";
import https from "node:https";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

/**
 * Memoria: what the Instance remembers between Sessions, kept in Understory. An admin's Agent asks
 * and writes it through three fixed tools that call Understory's MCP endpoint (`POST /mcp`, stateless
 * streamable HTTP, one JSON reply) directly; no MCP adapter, no `mcp.json`. See
 * `docs/deck/architecture.md`.
 *
 * - Admin only, checked twice: the factory is loaded only in a Session of an admin (`ToolProfile`)
 *   and only when Deck has `UNDERSTORY_TOKEN`; every call asks again whether the owner is an admin
 *   now, and no answer is a no.
 * - Reading does not taint the Session (the names are not an MCP proxy's). A tainted Session loses
 *   `add` and `update` whatever the input (`TAINT_REVOKED_TOOLS` in `guard.ts`): only clean Sessions
 *   write the Memoria. A subagent's child gets `query` alone (`MEMORIA_CHILD_TOOLS`).
 * - Understory down, or slow past the timeout (40 min: a query drives an LLM), is an error result for
 *   the Agent. Registering never reaches Understory, so neither a Session nor Deck waits on it.
 *
 * The daemon hands the URL per Platform (`understory_url` in its routing), read on every call;
 * the token comes from Deck's environment.
 */

/** The tools this factory registers, as the Agent sees them. */
export const MEMORIA_TOOLS: readonly string[] = ["understory_memory_query", "understory_memory_add", "understory_memory_update"];

/** What a subagent's child may call: reading only. */
export const MEMORIA_CHILD_TOOLS: readonly string[] = ["understory_memory_query"];

/** How long a call may take before it is an error: a query or a write runs an LLM inside Understory. */
export const MEMORIA_TIMEOUT_MS = 40 * 60_000;

/** How Deck reaches Understory: the token from its environment, the URL the daemon hands it now. */
export interface MemoriaAccess {
  token: string;
  /** Understory's base URL, or `null` when the daemon says it is off; throws when it cannot be read. */
  url: () => Promise<string | null>;
}

export interface MemoriaOptions extends MemoriaAccess {
  /** Whether the Session's owner is an admin right now: asked before every call. */
  adminNow: () => Promise<boolean>;
  /** Overrides `MEMORIA_TIMEOUT_MS` (tests). */
  timeoutMs?: number;
}

const textResult = (text: string) => ({ content: [{ type: "text" as const, text }], details: {} });

/** One JSON-RPC exchange over HTTP, without fetch's 5-minute header timeout: only `timeoutMs` and the abort end it. */
function post(url: URL, token: string, body: string, signal: AbortSignal): Promise<{ status: number; text: string }> {
  return new Promise((resolve, reject) => {
    const req = (url.protocol === "https:" ? https : http).request(
      url,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json, text/event-stream",
          Authorization: `Bearer ${token}`,
          "Content-Length": Buffer.byteLength(body),
        },
        signal,
      },
      (res) => {
        let text = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => (text += chunk));
        res.on("end", () => resolve({ status: res.statusCode ?? 0, text }));
        res.on("error", reject);
      },
    );
    req.on("error", reject);
    req.end(body);
  });
}

/** An ExtensionFactory (pi's inline extension), one instance per admin Session; `tools` narrows what it registers. */
export function memoriaExtension(opts: MemoriaOptions, tools: readonly string[] = MEMORIA_TOOLS) {
  const timeoutMs = opts.timeoutMs ?? MEMORIA_TIMEOUT_MS;

  /** Fails closed: a member now, a gone owner or an identity that does not answer all refuse. */
  async function requireAdmin(): Promise<void> {
    let admin = false;
    try {
      admin = await opts.adminNow();
    } catch {
      admin = false;
    }
    if (!admin) throw new Error("Refused: Memoria is for an admin, and the owner of this Session is not one now (or that could not be checked).");
  }

  async function endpoint(): Promise<URL> {
    let raw: string | null;
    try {
      raw = await opts.url();
    } catch (err) {
      throw new Error(`Memoria is unavailable: where Understory is could not be read (${err instanceof Error ? err.message : err}).`);
    }
    if (!raw) throw new Error("Memoria is unavailable: Understory is off on this Instance.");
    let url: URL;
    try {
      url = new URL("mcp", raw.endsWith("/") ? raw : `${raw}/`);
    } catch {
      throw new Error(`Memoria is unavailable: "${raw}" is not a URL.`);
    }
    if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error(`Memoria is unavailable: "${raw}" is not http(s).`);
    return url;
  }

  /** Calls one of Understory's MCP tools and returns its text, or throws what the Agent should read. */
  async function call(tool: string, args: Record<string, unknown>, signal: AbortSignal | undefined): Promise<string> {
    await requireAdmin();
    const url = await endpoint();
    const timeout = AbortSignal.timeout(timeoutMs);
    const body = JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: tool, arguments: args } });
    let res: { status: number; text: string };
    try {
      res = await post(url, opts.token, body, signal ? AbortSignal.any([signal, timeout]) : timeout);
    } catch (err) {
      if (timeout.aborted) throw new Error(`Understory did not answer within ${Math.round(timeoutMs / 60_000)} min; the Memoria call was dropped.`);
      if (signal?.aborted) throw new Error("Memoria call aborted.");
      const detail = err instanceof Error ? err.message : String(err);
      throw new Error(`Could not reach Understory (${detail}). The Session goes on without Memoria; tell the admin instead of retrying.`);
    }
    if (res.status === 401) throw new Error("Understory refused the token (401): Deck and Understory do not share UNDERSTORY_TOKEN. Needs the admin, not a retry.");
    if (res.status < 200 || res.status >= 300) throw new Error(`Understory answered ${res.status}: ${res.text.slice(0, 500) || "(empty)"}`);
    let rpc: any;
    try {
      rpc = JSON.parse(res.text);
    } catch {
      throw new Error("Understory answered something that is not JSON-RPC.");
    }
    if (rpc?.error) throw new Error(`Understory refused the call: ${rpc.error.message ?? JSON.stringify(rpc.error)}`);
    const content: any[] = Array.isArray(rpc?.result?.content) ? rpc.result.content : [];
    const text = content.filter((c) => c?.type === "text").map((c) => String(c.text)).join("\n");
    if (rpc?.result?.isError) throw new Error(text || "Understory reported an error.");
    return text || "(empty answer)";
  }

  const all = [
    {
      name: "understory_memory_query",
      label: "Memoria: consultar",
      description:
        "Ask the Instance's Memoria (what it remembers between Sessions, kept in Understory) a natural-language " +
        "question. An agent inside Understory searches it and answers with cited paths. One fact or concept per call. " +
        "Can be slow: it runs a model.",
      parameters: Type.Object({ question: Type.String({ description: "The question to answer" }) }),
      args: (p: any) => ({ question: p.question }),
      tool: "memory_query",
    },
    {
      name: "understory_memory_add",
      label: "Memoria: agregar",
      description:
        "Record new knowledge in the Instance's Memoria (facts, decisions, runbooks), in any prose form. Use " +
        "understory_memory_update when the concept already exists. Not available once this Session has read untrusted content.",
      parameters: Type.Object({
        content: Type.String({ description: "The knowledge to record, in any prose form" }),
        suggested_path: Type.Optional(Type.String({ description: 'Optional path hint in the memory, e.g. "/apis/payments.md"' })),
      }),
      args: (p: any) => (p.suggested_path ? { content: p.content, suggested_path: p.suggested_path } : { content: p.content }),
      tool: "memory_add",
    },
    {
      name: "understory_memory_update",
      label: "Memoria: corregir",
      description:
        "Change existing knowledge in the Instance's Memoria (correct a fact, deprecate a concept, restructure), " +
        "described in natural language. Not available once this Session has read untrusted content.",
      parameters: Type.Object({ instruction: Type.String({ description: "What to change, in natural language" }) }),
      args: (p: any) => ({ instruction: p.instruction }),
      tool: "memory_update",
    },
  ];

  return (pi: ExtensionAPI): void => {
    for (const t of all) {
      if (!tools.includes(t.name)) continue;
      pi.registerTool({
        name: t.name,
        label: t.label,
        description: t.description,
        parameters: t.parameters,
        execute: async (_toolCallId: string, params: any, signal: AbortSignal | undefined) => textResult(await call(t.tool, t.args(params), signal)),
      });
    }
  };
}
