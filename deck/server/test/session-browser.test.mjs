import test from "node:test";
import assert from "node:assert/strict";
import { sessionBrowserNow } from "../dist/session-browser.js";
import { InMemorySessionIdentity } from "../dist/session-identity.js";

const CDP = "http://127.0.0.1:9222";

const gate = (over = {}) => {
  const identity = over.identity ?? new InMemorySessionIdentity().add(7, "admin").add(8, "miembro");
  return sessionBrowserNow({
    owner: 7,
    identity,
    on: async () => true,
    allowlist: async () => ["*.example.com"],
    cdpEndpoint: CDP,
    ...over,
  });
};

test("session browser: an admin's Session with the browser on drives the Instance browser, at its fixed CDP endpoint", async () => {
  const now = await gate()();
  assert.deepEqual(now, { allowed: true, allowlist: ["*.example.com"], cdpEndpoint: CDP });
});

test("session browser: two admins' Sessions share the one Instance browser, with no lease", async () => {
  const identity = new InMemorySessionIdentity().add(7, "admin").add(9, "admin");
  const a = await gate({ identity, owner: 7 })();
  const b = await gate({ identity, owner: 9 })();
  assert.equal(a.cdpEndpoint, CDP);
  assert.equal(b.cdpEndpoint, CDP);
});

test("session browser: with the Session's toggle off the gate is shut", async () => {
  assert.deepEqual(await gate({ on: async () => false })(), { allowed: false, allowlist: [] });
});

test("session browser: a Session with no owner never opens the browser", async () => {
  assert.equal((await gate({ owner: null })()).allowed, false);
});

test("session browser: a miembro's Session, toggle on, is shut", async () => {
  assert.equal((await gate({ owner: 8 })()).allowed, false);
});

test("session browser: the role is read at each call, so an admin demoted mid-Session loses the browser on the next one", async () => {
  const identity = new InMemorySessionIdentity().add(7, "admin");
  const now = gate({ identity });
  assert.equal((await now()).allowed, true);
  identity.setRole(7, "miembro");
  assert.equal((await now()).allowed, false);
  identity.setRole(7, "admin");
  assert.equal((await now()).allowed, true);
});

test("session browser: an owner gone, disabled, or an identity that does not answer, shuts the gate (fails closed)", async () => {
  const identity = new InMemorySessionIdentity().add(7, "admin");
  const now = gate({ identity });
  identity.disable(7);
  assert.equal((await now()).allowed, false);
  identity.add(7, "admin").down();
  assert.equal((await now()).allowed, false);
  identity.up().remove(7);
  assert.equal((await now()).allowed, false);
});

test("session browser: a toggle or allowlist that cannot be read shuts the gate", async () => {
  assert.equal((await gate({ on: async () => { throw new Error("store down"); } })()).allowed, false);
  assert.equal((await gate({ allowlist: async () => { throw new Error("store down"); } })()).allowed, false);
});
