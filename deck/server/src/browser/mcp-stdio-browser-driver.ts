import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import readline from "node:readline";
import type { BrowserDriver, BrowserToolResult, BrowserToolSpec } from "../browser-driver.js";

export interface McpStdioBrowserDriverOptions {
  command: string;
  /** Arguments that start one MCP server on this CDP endpoint. */
  args: (endpoint: string) => string[];
  /** Arguments for the throwaway server that only lists tools, with no browser behind it. */
  probeArgs?: () => string[];
  callTimeoutMs: number;
  /** Told of each process started; for tests that check none is left behind. */
  onSpawn?: (pid: number) => void;
}

/** One MCP server over stdio (newline-delimited JSON-RPC), started for one CDP endpoint. */
class McpProcess {
  private child: ChildProcessWithoutNullStreams;
  private nextId = 1;
  private waiting = new Map<number, { resolve: (v: any) => void; reject: (e: Error) => void }>();
  private ready: Promise<void>;
  dead = false;

  constructor(command: string, args: string[], private timeoutMs: number, onSpawn?: (pid: number) => void, private onGone: () => void = () => {}) {
    this.child = spawn(command, args, { stdio: ["pipe", "pipe", "pipe"] });
    if (this.child.pid !== undefined) onSpawn?.(this.child.pid);
    this.child.stderr.resume();
    // EPIPE after the process is gone is the same news as its exit.
    this.child.stdin.on("error", () => {});
    readline.createInterface({ input: this.child.stdout }).on("line", (line) => this.onLine(line));
    const gone = (why: string) => {
      this.dead = true;
      for (const w of this.waiting.values()) w.reject(new Error(why));
      this.waiting.clear();
      this.onGone();
    };
    this.child.on("error", (e) => gone(`Could not start the browser tools: ${e.message}`));
    this.child.on("exit", () => gone("The browser tools stopped"));
    this.ready = this.request("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "deck", version: "1" },
    }).then(() => this.write({ jsonrpc: "2.0", method: "notifications/initialized" }));
    // Whoever calls later sees the failure through `call`; until then it is not an unhandled rejection.
    this.ready.catch(() => {});
  }

  private write(message: object): void {
    if (!this.dead) this.child.stdin.write(JSON.stringify(message) + "\n");
  }

  private onLine(line: string): void {
    let msg: any;
    try {
      msg = JSON.parse(line);
    } catch {
      return;
    }
    const waiter = typeof msg.id === "number" ? this.waiting.get(msg.id) : undefined;
    if (!waiter) return;
    this.waiting.delete(msg.id);
    if (msg.error) waiter.reject(new Error(String(msg.error.message ?? "MCP error")));
    else waiter.resolve(msg.result);
  }

  private request(method: string, params?: object): Promise<any> {
    if (this.dead) return Promise.reject(new Error("The browser tools stopped"));
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.waiting.delete(id);
        // A server that stopped answering is not trusted with the next call either.
        this.close();
        reject(new Error(`${method} timed out`));
      }, this.timeoutMs);
      this.waiting.set(id, {
        resolve: (v) => (clearTimeout(timer), resolve(v)),
        reject: (e) => (clearTimeout(timer), reject(e)),
      });
      this.write({ jsonrpc: "2.0", id, method, ...(params ? { params } : {}) });
    });
  }

  async call(method: string, params?: object): Promise<any> {
    await this.ready;
    return this.request(method, params);
  }

  close(): void {
    this.dead = true;
    this.child.kill();
  }
}

/**
 * Drives Playwright's MCP server (or any MCP server that takes the same CDP flag) with one process
 * per endpoint, started on first use. The Instance browser has one endpoint, so every Session shares
 * one process and its tabs. Inline, with no `mcp.json` and no MCP adapter.
 */
export class McpStdioBrowserDriver implements BrowserDriver {
  private servers = new Map<string, McpProcess>();
  private tools?: Promise<BrowserToolSpec[]>;

  constructor(private opts: McpStdioBrowserDriverOptions) {}

  catalogue(): Promise<BrowserToolSpec[]> {
    this.tools ??= this.list().catch((e) => {
      this.tools = undefined;
      throw e;
    });
    return this.tools;
  }

  private async list(): Promise<BrowserToolSpec[]> {
    const probe = this.start(this.opts.probeArgs?.() ?? []);
    try {
      const result = await probe.call("tools/list");
      return (result.tools ?? []) as BrowserToolSpec[];
    } finally {
      probe.close();
    }
  }

  private start(args: string[], endpoint?: string): McpProcess {
    const proc: McpProcess = new McpProcess(this.opts.command, args, this.opts.callTimeoutMs, this.opts.onSpawn, () => {
      // A process that is gone is not kept for the next call to find dead.
      if (endpoint !== undefined && this.servers.get(endpoint) === proc) this.servers.delete(endpoint);
    });
    return proc;
  }

  async call(endpoint: string, tool: string, args: Record<string, unknown>): Promise<BrowserToolResult> {
    let server = this.servers.get(endpoint);
    if (!server || server.dead) {
      server = this.start(this.opts.args(endpoint), endpoint);
      this.servers.set(endpoint, server);
    }
    const result = await server.call("tools/call", { name: tool, arguments: args });
    return { content: result.content ?? [], isError: result.isError === true };
  }

  async release(endpoint: string): Promise<void> {
    this.servers.get(endpoint)?.close();
    this.servers.delete(endpoint);
  }

  close(): void {
    for (const server of this.servers.values()) server.close();
    this.servers.clear();
  }
}
