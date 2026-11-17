import test from "node:test";
import assert from "node:assert/strict";
import { guardExtension } from "../dist/pi/guard.js";
import { SessionTaint } from "../dist/pi/session-taint.js";
import { createMemoryStore } from "../dist/store/memory/index.js";

const OPEN = { allowed: true, allowlist: [], cdpEndpoint: "http://127.0.0.1:9222" };

/** A stand-in for pi's extension API: keeps the handlers the Guard registers. */
const load = async ({ owned, gate = OPEN, allowedTools, browser = true } = {}) => {
  const store = createMemoryStore();
  await store.sessions.create({ id: "s1", title: "s1", workspace: "/w", executor: "host" });
  const handlers = {};
  const reported = [];
  const taint = new SessionTaint("s1", store.sessionTaint, { browserTools: owned });
  guardExtension({
    sessionId: "s1",
    report: (n) => reported.push(n),
    allowedTools,
    taint,
    browser: browser ? { owned: owned ?? new Set(), now: async () => gate } : undefined,
  })({ on: (name, fn) => (handlers[name] = fn) });
  await handlers.session_start({}, { sessionManager: { getEntries: () => [] } });
  return {
    reported,
    taint,
    call: (toolName, input = {}) => handlers.tool_call({ toolName, input }),
    result: (toolName, text = "page words", input = {}) =>
      handlers.tool_result({ toolName, input, isError: false, content: [{ type: "text", text }] }),
  };
};

test("guard: the Session's own browser tools are let through when its gate is open", async () => {
  const g = await load({ owned: new Set(["browser_navigate"]) });
  assert.equal(await g.call("browser_navigate", { url: "https://a.example" }), undefined);
  assert.deepEqual(g.reported.at(-1), { tool: "browser_navigate", verdict: "allow", reason: "" });
});

test("guard: a browser tool that is not the Session's own (another MCP's, the adapter's proxy) is refused", async () => {
  const g = await load({ owned: new Set(["browser_navigate"]) });
  for (const [tool, input] of [["browser_browser_navigate", {}], ["playwright_browser_click", {}], ["mcp", { server: "browser", tool: "browser_navigate" }]]) {
    const out = await g.call(tool, input);
    assert.equal(out?.block, true, tool);
    assert.match(out.reason, /Instance browser/);
  }
  assert.equal(g.reported.filter((r) => r.verdict === "deny").length, 3);
});

test("guard: a browser tool the Session does not own (file upload, left out of its registry) is refused", async () => {
  const g = await load({ owned: new Set(["browser_navigate"]) });
  assert.equal((await g.call("browser_file_upload", { paths: ["/app/package.json"] })).block, true);
});

test("guard: with no tools of its own (the catalogue failed, or no Instance browser wired) every browser call is refused", async () => {
  assert.equal((await (await load({ owned: new Set() })).call("browser_navigate", { url: "https://a.example" })).block, true);
  assert.equal((await (await load({ browser: false })).call("browser_navigate", { url: "https://a.example" })).block, true);
});

test("guard: an own tool with the gate shut (toggle off, owner not an admin now) is refused", async () => {
  const g = await load({ owned: new Set(["browser_navigate"]), gate: { allowed: false, allowlist: [] } });
  const out = await g.call("browser_navigate", { url: "https://a.example" });
  assert.equal(out.block, true);
  assert.match(out.reason, /cannot drive the browser/);
});

test("guard: a URL off the allowlist is refused, a sub of a glob is not", async () => {
  const g = await load({ owned: new Set(["browser_navigate"]), gate: { ...OPEN, allowlist: ["*.example.com"] } });
  assert.equal(await g.call("browser_navigate", { url: "https://docs.example.com/x" }), undefined);
  const out = await g.call("browser_navigate", { url: "https://evil.test" });
  assert.equal(out.block, true);
  assert.match(out.reason, /allowlist/);
});

test("guard: a closed profile's list still refuses browser tools first", async () => {
  const g = await load({ owned: new Set(["browser_navigate"]), allowedTools: new Set(["canvas_write"]) });
  assert.match((await g.call("browser_navigate", { url: "https://a.example" })).reason, /may only use canvas_write/);
});

test("guard: a decorated ref is normalised and a screenshot asks for inline image data", async () => {
  const g = await load({ owned: new Set(["browser_click", "browser_take_screenshot"]) });
  const click = { target: "[ref=f1e17]" };
  await g.call("browser_click", click);
  assert.equal(click.target, "f1e17");
  const shot = { filename: "page.jpg" };
  await g.call("browser_take_screenshot", shot);
  assert.deepEqual(shot, { type: "jpeg" });
});

test("guard: what the Session's own browser tools return is someone else's words, enveloped, and the Session tainted", async () => {
  const g = await load({ owned: new Set(["browser_snapshot"]) });
  const out = await g.result("browser_snapshot");
  assert.equal(out.content.length, 3);
  assert.equal(out.content[1].text, "page words");
  assert.equal(g.taint.isTainted(), true);
});

test("guard: a snapshot is compacted before it is enveloped", async () => {
  const g = await load({ owned: new Set(["browser_snapshot"]) });
  const out = await g.result("browser_snapshot", "### Snapshot\n```yaml\n- generic [ref=e1]: hi\n```");
  assert.match(out.content[1].text, /- : hi|\[e1\]/);
  assert.doesNotMatch(out.content[1].text, /ref=e1/);
});
