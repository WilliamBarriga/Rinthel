import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { browserDriverContract } from "./contract/browser-driver.mjs";
import { FakeBrowserDriver } from "./helpers/fake-browser-driver.mjs";
import { McpStdioBrowserDriver } from "../dist/extensions/mcp-stdio-browser-driver.js";

const tools = [
  { name: "echo", description: "Echo", inputSchema: { type: "object", properties: { text: { type: "string" } } } },
  { name: "fail", description: "Always fails", inputSchema: { type: "object", properties: {} } },
];

browserDriverContract("fake driver", async () => ({
  driver: new FakeBrowserDriver(tools, (endpoint, tool, args) =>
    tool === "fail"
      ? { content: [{ type: "text", text: "boom" }], isError: true }
      : { content: [{ type: "text", text: `${endpoint}|${args.text ?? ""}` }], isError: false }
  ),
}));

const server = fileURLToPath(new URL("./helpers/fake-mcp-server.mjs", import.meta.url));
browserDriverContract("stdio MCP driver", async () => {
  const driver = new McpStdioBrowserDriver({
    command: process.execPath,
    args: (endpoint) => [server, "--cdp-endpoint", endpoint],
    probeArgs: () => [server],
    callTimeoutMs: 5000,
  });
  return { driver, close: () => driver.close() };
});

const alive = (pid) => {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
};
const chaos = (t, over = {}) => {
  const pids = [];
  const driver = new McpStdioBrowserDriver({
    command: process.execPath,
    args: (endpoint) => [server, "--chaos", "--cdp-endpoint", endpoint],
    probeArgs: () => [server, "--chaos"],
    callTimeoutMs: 300,
    onSpawn: (pid) => pids.push(pid),
    ...over,
  });
  t.after(() => driver.close());
  return { driver, pids };
};
const gone = async (pid) => {
  const end = Date.now() + 2000;
  while (alive(pid) && Date.now() < end) await new Promise((r) => setTimeout(r, 20));
  return !alive(pid);
};

test("stdio MCP driver: a call that times out kills its process, and the endpoint works again afterwards", async (t) => {
  const { driver, pids } = chaos(t);
  const endpoint = "http://127.0.0.1:45002";
  await assert.rejects(driver.call(endpoint, "hang", {}), /timed out/);
  assert.equal(pids.length, 1);
  assert.ok(await gone(pids[0]));
  const again = await driver.call(endpoint, "echo", { text: "x" });
  assert.equal(again.content[0].text, `${endpoint}|x`);
});

test("stdio MCP driver: a process that died is replaced on the next call and does not leave an unhandled error", async (t) => {
  const { driver } = chaos(t);
  const endpoint = "http://127.0.0.1:45002";
  await assert.rejects(driver.call(endpoint, "die", {}), /stopped/);
  await new Promise((r) => setTimeout(r, 50));
  assert.equal((await driver.call(endpoint, "echo", { text: "x" })).isError, false);
});

test("stdio MCP driver: closing it leaves no process behind", async (t) => {
  const { driver, pids } = chaos(t);
  await driver.call("http://127.0.0.1:45002", "echo", { text: "a" });
  await driver.call("http://127.0.0.1:45012", "echo", { text: "b" });
  assert.equal(pids.length, 2);
  driver.close();
  for (const pid of pids) assert.ok(await gone(pid), `pid ${pid}`);
});

test("stdio MCP driver: a server that cannot start rejects the call instead of crashing Deck", async (t) => {
  const { driver } = chaos(t, { command: "/nonexistent/mcp-server" });
  await assert.rejects(driver.call("http://127.0.0.1:45002", "echo", {}), /Could not start|stopped/);
  await assert.rejects(driver.catalogue(), /Could not start|stopped/);
});
