/**
 * An Understory as Deck reaches it, over real HTTP: MCP's streamable HTTP at `POST /mcp`, stateless,
 * one JSON reply per request, as `understory/packages/server/src/mcp/http.ts` serves it. Behind
 * `Authorization: Bearer <token>` (`401` without the right one, as its `auth.ts`), it refuses a
 * request that does not accept both JSON and an event stream (`406`, as MCP's transport does), and
 * answers `tools/call` for its memory tools with a fixed text. No memory is read or written: every
 * call is recorded, so a test sees exactly what reached Understory and with which token.
 */
import { listen, readJson, sendJson as json } from "./http-fake.mts";

export interface MemoryCall { tool: string; arguments: Record<string, unknown> }

export interface FakeUnderstory {
  url: string;
  token: string;
  /** Every authorised `tools/call`, in order. */
  calls: MemoryCall[];
  /** Every request that reached it, authorised or not: `METHOD /path`. */
  requests: string[];
  /** What each tool answers; a tool without an answer is a failed mutation (`isError`). */
  answers: Record<string, string>;
  /** Milliseconds before it answers (a query drives an LLM: it can be slow). */
  delayMs: number;
  close(): Promise<void>;
}

const TOOLS = ["memory_query", "memory_add", "memory_update", "memory_status", "memory_maintain"];

export async function fakeUnderstory(token = "understory-test-token"): Promise<FakeUnderstory> {
  const state: Omit<FakeUnderstory, "url" | "close"> = {
    token,
    calls: [],
    requests: [],
    answers: {
      memory_query: "The Instance runs on Linux. (see /reference/host.md)",
      memory_add: "Recorded.\n\nFiles changed:\n- /reference/host.md",
      memory_update: "Updated.\n\nFiles changed:\n- /reference/host.md",
    },
    delayMs: 0,
  };
  const server = await listen(async (req, res) => {
    const url = new URL(req.url ?? "/", "http://understory");
    const rpc = await readJson(req);
    state.requests.push(`${req.method} ${url.pathname}`);
    if (url.pathname !== "/mcp") return json(res, 404, { error: "not found" });
    if (req.headers.authorization !== `Bearer ${state.token}`) {
      return json(res, 401, { error: "unauthorized: set Authorization: Bearer <AUTH_TOKEN>" });
    }
    const accept = String(req.headers.accept ?? "");
    if (req.method !== "POST" || !accept.includes("application/json") || !accept.includes("text/event-stream")) {
      return json(res, 406, { jsonrpc: "2.0", error: { code: -32000, message: "Not Acceptable" }, id: null });
    }
    if (rpc.method !== "tools/call") {
      return json(res, 200, { jsonrpc: "2.0", id: rpc.id, error: { code: -32601, message: "Method not found" } });
    }
    const tool = String(rpc.params?.name);
    if (!TOOLS.includes(tool)) {
      return json(res, 200, { jsonrpc: "2.0", id: rpc.id, error: { code: -32602, message: `Tool ${tool} not found` } });
    }
    state.calls.push({ tool, arguments: rpc.params?.arguments ?? {} });
    if (state.delayMs) await new Promise((r) => setTimeout(r, state.delayMs));
    if (res.destroyed) return;
    const answer = state.answers[tool];
    const result = answer === undefined
      ? { content: [{ type: "text", text: "Mutation failed: the bundle is read-only" }], isError: true }
      : { content: [{ type: "text", text: answer }] };
    json(res, 200, { jsonrpc: "2.0", id: rpc.id, result });
  });
  return Object.assign(state, { url: server.url, close: server.close });
}
