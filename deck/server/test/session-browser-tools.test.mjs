import test from "node:test";
import assert from "node:assert/strict";
import { EXCLUDE_TOOLS, sessionBrowserTools } from "../dist/pi/session-browser-tools.js";
import { FakeBrowserDriver } from "./helpers/fake-browser-driver.mjs";

const catalogue = [
  { name: "browser_navigate", description: "Go to a URL", inputSchema: { type: "object", properties: { url: { type: "string" } }, required: ["url"] } },
  { name: "browser_snapshot", description: "Read the page", inputSchema: { type: "object", properties: {} } },
];

/** A stand-in for pi's extension API: collects what the factory registers. */
const load = async (driver, now, options = {}) => {
  const tools = new Map();
  await sessionBrowserTools(driver, now, options)({ registerTool: (t) => tools.set(t.name, t) });
  return tools;
};
const CDP = "http://127.0.0.1:9222";
const open = async () => ({ allowed: true, allowlist: [], cdpEndpoint: CDP });
const shut = async () => ({ allowed: false, allowlist: [] });

test("session browser tools: every tool the driver offers is registered with its own schema", async () => {
  const tools = await load(new FakeBrowserDriver(catalogue), open);
  assert.deepEqual([...tools.keys()], ["browser_navigate", "browser_snapshot"]);
  assert.deepEqual(tools.get("browser_navigate").parameters, catalogue[0].inputSchema);
});

test("session browser tools: two Sessions' calls go to the one Instance browser the gate names", async () => {
  const driver = new FakeBrowserDriver(catalogue);
  const a = await load(driver, open);
  const b = await load(driver, open);
  await a.get("browser_navigate").execute("1", { url: "https://a.example" });
  await b.get("browser_navigate").execute("2", { url: "https://b.example" });
  assert.deepEqual(driver.calls.map((c) => [c.endpoint, c.tool, c.args.url]), [
    [CDP, "browser_navigate", "https://a.example"],
    [CDP, "browser_navigate", "https://b.example"],
  ]);
});

test("session browser tools: the page's answer comes back as the tool result", async () => {
  const driver = new FakeBrowserDriver(catalogue, () => ({ content: [{ type: "text", text: "- heading" }], isError: false }));
  const tools = await load(driver, open);
  const result = await tools.get("browser_snapshot").execute("1", {});
  assert.deepEqual(result.content, [{ type: "text", text: "- heading" }]);
});

test("session browser tools: a tool that fails in the browser fails the call", async () => {
  const driver = new FakeBrowserDriver(catalogue, () => ({ content: [{ type: "text", text: "Timeout" }], isError: true }));
  const tools = await load(driver, open);
  await assert.rejects(tools.get("browser_snapshot").execute("1", {}), /Timeout/);
});

test("session browser tools: with the gate shut the driver is never reached", async () => {
  const driver = new FakeBrowserDriver(catalogue);
  const tools = await load(driver, shut);
  await assert.rejects(tools.get("browser_navigate").execute("1", { url: "https://a.example" }), /no browser/i);
  assert.deepEqual(driver.calls, []);
});

test("session browser tools: the gate is read once per call (no heartbeat: the Instance browser has no idle clock)", async () => {
  let reads = 0;
  const driver = new FakeBrowserDriver(catalogue);
  driver.call = async () => {
    await new Promise((r) => setTimeout(r, 60));
    return { content: [], isError: false };
  };
  const tools = await load(driver, async () => (reads++, { allowed: true, allowlist: [], cdpEndpoint: CDP }));
  await tools.get("browser_snapshot").execute("1", {});
  assert.equal(reads, 1);
});

test("session browser tools: the names registered are published, for the Guard to tell them from any other browser tool", async () => {
  const owned = new Set();
  await load(new FakeBrowserDriver(catalogue), open, { owned });
  assert.deepEqual([...owned], ["browser_navigate", "browser_snapshot"]);
});

test("session browser tools: arbitrary code, file upload and drop are never registered", async () => {
  const schema = { type: "object", properties: {} };
  const driver = new FakeBrowserDriver(["browser_file_upload", "browser_drop", "browser_run_code_unsafe", "browser_click"].map((name) => ({ name, description: name, inputSchema: schema })));
  const owned = new Set();
  const tools = await load(driver, open, { owned });
  assert.deepEqual(EXCLUDE_TOOLS, ["browser_run_code_unsafe", "browser_file_upload", "browser_drop"]);
  assert.deepEqual([...tools.keys()], ["browser_click"]);
  assert.deepEqual([...owned], ["browser_click"]);
});

test("session browser tools: a driver that cannot list its tools leaves the Session without browser tools, not without a launch", async () => {
  const driver = new FakeBrowserDriver(catalogue);
  driver.catalogue = async () => { throw new Error("npx: offline"); };
  const errors = [];
  const owned = new Set();
  const tools = await load(driver, open, { owned, onError: (e) => errors.push(e.message) });
  assert.equal(tools.size, 0);
  assert.equal(owned.size, 0);
  assert.deepEqual(errors, ["npx: offline"]);
});
