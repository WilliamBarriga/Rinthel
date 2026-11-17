/**
 * A llama-server as Deck reaches it, over real HTTP: the OpenAI chat completions pi sends (streamed,
 * with `prompt_progress` when asked for `return_progress`), the slot actions `POST /slots/0?action=`
 * writing and reading `<slotDir>/<filename>` as `--slot-save-path` does, and `GET /slots`.
 * Upstream API: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
 *
 * `log` keeps the order things happened in (`restore x`, `completion <model>`, `save x`), which is
 * what the slot lock is about. `hold()` keeps the next completions open until released.
 */
import http from "node:http";
import { once } from "node:events";
import type { AddressInfo } from "node:net";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

export interface FakeLlama {
  url: string;
  log: string[];
  /** The bodies of every completion, parsed. */
  bodies: any[];
  /** What each completion answers, word by word. */
  answer: string[];
  /** Tool calls the next completions answer with, one per completion, before falling back to `answer`. */
  toolCalls: { name: string; arguments: Record<string, unknown> }[];
  /** Answer completions with this status instead (`null`: answer normally). */
  failWith: number | null;
  /** Keep every completion that starts from now on open until the returned function is called. */
  hold(): () => void;
  close(): Promise<void>;
}

const chunk = (model: string, delta: Record<string, unknown>, finish: string | null = null) =>
  `data: ${JSON.stringify({ id: "c1", object: "chat.completion.chunk", model, choices: [{ index: 0, delta, finish_reason: finish }] })}\n\n`;

export async function fakeLlama(slotDir: string, slotBytes = 64): Promise<FakeLlama> {
  mkdirSync(slotDir, { recursive: true });
  let gate: Promise<void> | null = null;
  const state = {
    log: [] as string[],
    bodies: [] as any[],
    answer: ["hola"],
    toolCalls: [] as { name: string; arguments: Record<string, unknown> }[],
    failWith: null as number | null,
  };
  let calls = 0;
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", "http://llama");
    let raw = "";
    for await (const c of req) raw += c;
    const body = raw ? JSON.parse(raw) : {};
    if (req.method === "POST" && url.pathname === "/slots/0") {
      const action = url.searchParams.get("action");
      const file = path.join(slotDir, String(body.filename));
      state.log.push(`${action} ${String(body.filename).replace(/\.bin$/, "")}`);
      if (action === "save") {
        writeFileSync(file, Buffer.alloc(slotBytes, 1));
        return void res.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify({ id_slot: 0, filename: body.filename, n_saved: 12, n_written: slotBytes }));
      }
      if (action === "restore") {
        if (!existsSync(file)) return void res.writeHead(400, { "content-type": "application/json" }).end('{"error":{"message":"failed to restore"}}');
        return void res.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify({ id_slot: 0, filename: body.filename, n_restored: 12, n_read: slotBytes }));
      }
      return void res.writeHead(400).end();
    }
    if (req.method === "GET" && url.pathname === "/slots") {
      return void res.writeHead(200, { "content-type": "application/json" }).end('[{"id":0,"is_processing":false}]');
    }
    if (req.method === "POST" && url.pathname === "/v1/chat/completions") {
      state.bodies.push(body);
      state.log.push(`completion ${body.model}`);
      const held = gate;
      if (held) await held;
      if (state.failWith) {
        return void res.writeHead(state.failWith, { "content-type": "application/json" }).end('{"error":{"message":"llama failed"}}');
      }
      if (!body.stream) {
        return void res.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify({
          id: "c1", object: "chat.completion", model: body.model,
          choices: [{ index: 0, message: { role: "assistant", content: state.answer.join("") }, finish_reason: "stop" }],
        }));
      }
      res.writeHead(200, { "content-type": "text/event-stream" });
      if (body.return_progress) {
        res.write(`data: ${JSON.stringify({ prompt_progress: { total: 100, cache: 60, processed: 100, time_ms: 40 } })}\n\n`);
      }
      res.write(chunk(body.model, { role: "assistant", content: "" }));
      const toolCall = state.toolCalls.shift();
      if (toolCall) {
        const call = { index: 0, id: `call_${++calls}`, type: "function", function: { name: toolCall.name, arguments: JSON.stringify(toolCall.arguments) } };
        res.write(chunk(body.model, { tool_calls: [call] }));
        res.write(chunk(body.model, {}, "tool_calls"));
        res.end("data: [DONE]\n\n");
        return;
      }
      for (const word of state.answer) res.write(chunk(body.model, { content: word }));
      res.write(chunk(body.model, {}, "stop"));
      res.end("data: [DONE]\n\n");
      return;
    }
    res.writeHead(404).end();
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  return {
    url: `http://127.0.0.1:${(server.address() as AddressInfo).port}`,
    get log() { return state.log; },
    get bodies() { return state.bodies; },
    get answer() { return state.answer; },
    set answer(words: string[]) { state.answer = words; },
    get toolCalls() { return state.toolCalls; },
    set toolCalls(calls) { state.toolCalls = calls; },
    get failWith() { return state.failWith; },
    set failWith(status: number | null) { state.failWith = status; },
    hold() {
      let release!: () => void;
      gate = new Promise<void>((r) => { release = r; });
      return () => { gate = null; release(); };
    },
    close: async () => {
      server.closeAllConnections();
      await new Promise<void>((r) => server.close(() => r()));
    },
  };
}
