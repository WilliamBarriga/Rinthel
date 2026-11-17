import test from "node:test";
import assert from "node:assert/strict";

/**
 * Contract for `BrowserDriver`. `open()` gives `{ driver, close? }` over a browser whose tools are
 * `echo` (answers `<endpoint>|<text>`) and `fail` (always an error result).
 */
export function browserDriverContract(name, open) {
  const fresh = async (t) => {
    const opened = await open();
    t.after(() => opened.close?.());
    return opened.driver;
  };
  const text = (r) => r.content.map((c) => c.text).join("");

  test(`${name}: the catalogue lists the tools with their schemas`, async (t) => {
    const driver = await fresh(t);
    const tools = await driver.catalogue();
    assert.deepEqual(tools.map((x) => x.name).sort(), ["echo", "fail"]);
    assert.equal(tools.find((x) => x.name === "echo").inputSchema.type, "object");
  });

  test(`${name}: a call acts on the endpoint it names`, async (t) => {
    const driver = await fresh(t);
    assert.equal(text(await driver.call("http://127.0.0.1:45002", "echo", { text: "a" })), "http://127.0.0.1:45002|a");
    assert.equal(text(await driver.call("http://127.0.0.1:45012", "echo", { text: "b" })), "http://127.0.0.1:45012|b");
    assert.equal(text(await driver.call("http://127.0.0.1:45002", "echo", { text: "c" })), "http://127.0.0.1:45002|c");
  });

  test(`${name}: a tool that fails comes back as an error result, not a throw`, async (t) => {
    const driver = await fresh(t);
    const result = await driver.call("http://127.0.0.1:45002", "fail", {});
    assert.equal(result.isError, true);
    assert.equal(text(result), "boom");
  });

  test(`${name}: after release the endpoint can be used again`, async (t) => {
    const driver = await fresh(t);
    await driver.call("http://127.0.0.1:45002", "echo", { text: "a" });
    await driver.release("http://127.0.0.1:45002");
    await driver.release("http://127.0.0.1:45099"); // never used: not an error
    assert.equal(text(await driver.call("http://127.0.0.1:45002", "echo", { text: "b" })), "http://127.0.0.1:45002|b");
  });
}
