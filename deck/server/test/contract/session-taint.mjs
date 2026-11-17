import test from "node:test";
import assert from "node:assert/strict";

/** Contract for `store.sessionTaint`: a Session's taint mark, written once and kept for good. */
export function sessionTaintContract(open) {
  const fresh = async (t) => {
    const store = await open();
    t.after(() => store.close());
    for (const id of ["s1", "s2"]) await store.sessions.create({ id, title: id, workspace: "/work", executor: "host" });
    return store;
  };

  test("sessionTaint: a Session is clean until marked, and the mark is its own", async (t) => {
    const store = await fresh(t);
    assert.equal(await store.sessionTaint.isTainted("s1"), false);
    await store.sessionTaint.markTainted("s1");
    assert.equal(await store.sessionTaint.isTainted("s1"), true);
    assert.equal(await store.sessionTaint.isTainted("s2"), false);
  });

  test("sessionTaint: marking again changes nothing", async (t) => {
    const store = await fresh(t);
    await store.sessionTaint.markTainted("s1");
    await store.sessionTaint.markTainted("s1");
    assert.equal(await store.sessionTaint.isTainted("s1"), true);
  });

  test("sessionTaint: a Session that does not exist cannot be marked", async (t) => {
    const store = await fresh(t);
    await assert.rejects(() => store.sessionTaint.markTainted("nope"));
    assert.equal(await store.sessionTaint.isTainted("nope"), false);
  });

  test("sessionTaint: the mark goes with its Session, and a new one by the same id starts clean", async (t) => {
    const store = await fresh(t);
    await store.sessionTaint.markTainted("s1");
    await store.sessions.delete("s1");
    assert.equal(await store.sessionTaint.isTainted("s1"), false);
    await store.sessions.create({ id: "s1", title: "s1", workspace: "/work", executor: "host" });
    assert.equal(await store.sessionTaint.isTainted("s1"), false);
  });
}
