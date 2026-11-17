// A stdio MCP server that stands in for @playwright/mcp: newline-delimited JSON-RPC, and a tool that
// answers with the --cdp-endpoint it was started with, so a test can tell whose browser it reached.
import readline from "node:readline";

const at = process.argv.indexOf("--cdp-endpoint");
const endpoint = at >= 0 ? process.argv[at + 1] : "none";
const tools = [
  { name: "echo", description: "Echo", inputSchema: { type: "object", properties: { text: { type: "string" } } } },
  { name: "fail", description: "Always fails", inputSchema: { type: "object", properties: {} } },
];
if (process.argv.includes("--chaos")) {
  tools.push({ name: "hang", description: "Never answers", inputSchema: { type: "object", properties: {} } });
  tools.push({ name: "die", description: "Exits", inputSchema: { type: "object", properties: {} } });
}
const send = (m) => process.stdout.write(JSON.stringify({ jsonrpc: "2.0", ...m }) + "\n");

readline.createInterface({ input: process.stdin }).on("line", (line) => {
  const msg = JSON.parse(line);
  if (msg.id === undefined) return;
  if (msg.method === "initialize") {
    return send({ id: msg.id, result: { protocolVersion: "2024-11-05", capabilities: { tools: {} }, serverInfo: { name: "fake", version: "1" } } });
  }
  if (msg.method === "tools/list") return send({ id: msg.id, result: { tools } });
  if (msg.method === "tools/call") {
    const { name, arguments: args } = msg.params;
    if (name === "hang") return;
    if (name === "die") process.exit(1);
    if (name === "fail") return send({ id: msg.id, result: { content: [{ type: "text", text: "boom" }], isError: true } });
    return send({ id: msg.id, result: { content: [{ type: "text", text: `${endpoint}|${args?.text ?? ""}` }] } });
  }
  send({ id: msg.id, error: { code: -32601, message: "unknown method" } });
});
