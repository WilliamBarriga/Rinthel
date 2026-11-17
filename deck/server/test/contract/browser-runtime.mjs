import test from "node:test";
import assert from "node:assert/strict";

/**
 * Contract for `BrowserRuntime` in a mode Deck manages (docker). `open()` gives `{ runtime, close? }`
 * over a place where a browser can run and none is installed yet.
 */
export function browserRuntimeContract(name, open) {
  const fresh = async (t) => {
    const opened = await open();
    t.after(() => opened.close?.());
    return opened.runtime;
  };
  const cfg = (password = "s3cret") => ({ user: "agent", password, port: "3010", httpsPort: "3011" });

  test(`${name}: nothing is installed until the admin asks`, async (t) => {
    const runtime = await fresh(t);
    const s = await runtime.status();
    assert.equal(s.available, true);
    assert.equal(s.container, "absent");
  });

  test(`${name}: installing with no password is refused, and nothing is created`, async (t) => {
    const runtime = await fresh(t);
    await assert.rejects(runtime.install(cfg("")), /password/i);
    assert.equal((await runtime.status()).container, "absent");
  });

  test(`${name}: install runs it; stop and start move it; remove leaves it absent`, async (t) => {
    const runtime = await fresh(t);
    await runtime.install(cfg());
    assert.equal((await runtime.status()).container, "running");
    await runtime.stop();
    assert.equal((await runtime.status()).container, "stopped");
    await runtime.start();
    await runtime.start();
    assert.equal((await runtime.status()).container, "running");
    await runtime.remove();
    assert.equal((await runtime.status()).container, "absent");
  });

  test(`${name}: start and stop with nothing installed are refused`, async (t) => {
    const runtime = await fresh(t);
    await assert.rejects(runtime.start());
    await assert.rejects(runtime.stop());
  });

  test(`${name}: forgetting the profile removes the browser as well`, async (t) => {
    const runtime = await fresh(t);
    await runtime.install(cfg());
    await runtime.forgetProfile();
    assert.equal((await runtime.status()).container, "absent");
  });
}
