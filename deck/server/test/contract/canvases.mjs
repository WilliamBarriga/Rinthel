import test from "node:test";
import assert from "node:assert/strict";

const canvas = (over = {}) => ({
  id: "c1",
  session_id: "s1",
  kind: "markdown",
  title: "Notes",
  content: "hello",
  revision: 1,
  status: "saved",
  active_call: null,
  updated_at: "2026-01-01T00:00:00.000Z",
  ...over,
});

/** Contract for `store.canvases`: canvases that were saved, scoped to their session. */
export function canvasesContract(open) {
  const fresh = async (t) => {
    const store = await open();
    t.after(() => store.close());
    // A canvas hangs off a session that exists.
    for (const id of ["s1", "s2"]) await store.sessions.create({ id, title: id, workspace: "/work", executor: "host" });
    return store.canvases;
  };

  test("canvases: an inserted canvas is read back by its session and id, and only there", async (t) => {
    const canvases = await fresh(t);
    await canvases.insert(canvas());
    assert.deepEqual(await canvases.get("s1", "c1"), canvas());
    assert.equal(await canvases.get("s2", "c1"), undefined);
    assert.equal(await canvases.get("s1", "nope"), undefined);
  });

  test("canvases: the kind of a canvas, markdown or ui, is stored and read back", async (t) => {
    const canvases = await fresh(t);
    await canvases.insert(canvas({ id: "m" }));
    await canvases.insert(canvas({ id: "u", kind: "ui", content: '{"root":"r","elements":{}}' }));
    assert.equal((await canvases.get("s1", "m")).kind, "markdown");
    assert.equal((await canvases.get("s1", "u")).kind, "ui");
    assert.deepEqual((await canvases.list("s1")).map((c) => c.kind).sort(), ["markdown", "ui"]);
  });

  test("canvases: an unknown kind is refused", async (t) => {
    const canvases = await fresh(t);
    await assert.rejects(canvases.insert(canvas({ kind: "html" })));
    assert.equal(await canvases.get("s1", "c1"), undefined);
  });

  test("canvases: a session lists only its own", async (t) => {
    const canvases = await fresh(t);
    await canvases.insert(canvas({ id: "a" }));
    await canvases.insert(canvas({ id: "b" }));
    await canvases.insert(canvas({ id: "c", session_id: "s2" }));
    assert.deepEqual((await canvases.list("s1")).map((c) => c.id).sort(), ["a", "b"]);
  });

  test("canvases: update writes every field of the canvas in its own session", async (t) => {
    const canvases = await fresh(t);
    await canvases.insert(canvas());
    const next = canvas({ title: "New", content: "changed", revision: 2, status: "writing", active_call: "call-1", updated_at: "2026-02-02T00:00:00.000Z" });
    await canvases.update(next);
    assert.deepEqual(await canvases.get("s1", "c1"), next);

    await canvases.update(canvas({ session_id: "s2", title: "Hijack" }));
    assert.equal((await canvases.get("s1", "c1")).title, "New");
  });

  test("canvases: delete removes it only from its own session", async (t) => {
    const canvases = await fresh(t);
    await canvases.insert(canvas());
    await canvases.delete("s2", "c1");
    assert.ok(await canvases.get("s1", "c1"));
    await canvases.delete("s1", "c1");
    assert.equal(await canvases.get("s1", "c1"), undefined);
  });

  test("canvases: a write cut short by a restart is marked interrupted", async (t) => {
    const canvases = await fresh(t);
    await canvases.insert(canvas({ id: "busy", revision: 4, status: "writing", active_call: "call-1" }));
    await canvases.insert(canvas({ id: "idle" }));
    await canvases.interruptActiveWrites();

    const busy = await canvases.get("s1", "busy");
    assert.deepEqual([busy.status, busy.active_call, busy.revision], ["interrupted", null, 4]);
    assert.deepEqual(await canvases.get("s1", "idle"), canvas({ id: "idle" }));
  });

  test("canvases: a canvas belongs to a session that exists, and its id to one canvas", async (t) => {
    const canvases = await fresh(t);
    await assert.rejects(canvases.insert(canvas({ session_id: "nope" })));
    await canvases.insert(canvas());
    await assert.rejects(canvases.insert(canvas({ session_id: "s2" })));
    assert.deepEqual(await canvases.get("s1", "c1"), canvas());
  });

  test("canvases: updating one that is not there writes nothing", async (t) => {
    const canvases = await fresh(t);
    await canvases.update(canvas());
    assert.deepEqual(await canvases.list("s1"), []);
  });
}
