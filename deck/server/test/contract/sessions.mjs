import test from "node:test";
import assert from "node:assert/strict";

const make = (sessions, id, over = {}) =>
  sessions.create({ id, title: `Session ${id}`, workspace: "/work", executor: "host", ...over });

/** Contract for `store.sessions`: chat sessions and what hangs off them. */
export function sessionsContract(open) {
  const fresh = async (t) => {
    const store = await open();
    t.after(() => store.close());
    return store;
  };

  test("sessions: durable event existence is isolated by session and event type", async t => {
    const { sessions } = await fresh(t);
    await make(sessions, "s1"); await make(sessions, "s2");
    assert.equal(await sessions.hasEvent("s1", "portal_guard"), false);
    await sessions.appendEvent("s1", "portal_guard", { verdict: "deny" });
    assert.equal(await sessions.hasEvent("s1", "portal_guard"), true);
    assert.equal(await sessions.hasEvent("s2", "portal_guard"), false);
    assert.equal(await sessions.hasEvent("s1", "portal_route"), false);
  });

  test("sessions: a created session is an idle task with nothing attached, until told otherwise", async (t) => {
    const { sessions } = await fresh(t);
    await make(sessions, "s1");
    const row = await sessions.get("s1");
    assert.deepEqual(
      { title: row.title, workspace: row.workspace, executor: row.executor, status: row.status, kind: row.kind, pinned: row.pinned, browser: row.browser, staff_framing_sent: row.staff_framing_sent },
      { title: "Session s1", workspace: "/work", executor: "host", status: "idle", kind: "task", pinned: 0, browser: 0, staff_framing_sent: 0 },
    );
    for (const nullable of ["last_error", "provider", "model", "thinking_level", "pi_session_file", "owner_user_id"]) {
      assert.equal(row[nullable], null, nullable);
    }
    for (const gone of ["channel_slug", "channel_key", "channel_kind", "channel_ref", "archived_at"]) {
      assert.equal(gone in row, false, `${gone} is not a column`);
    }
    assert.match(row.created_at, /^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/);
    assert.match(row.updated_at, /^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/);
    assert.equal(await sessions.get("nope"), undefined);
  });

  test("sessions: the list is the tasks only, pinned first, an owner sees only theirs, and listOwnedBy gives every kind of theirs", async (t) => {
    const { sessions } = await fresh(t);
    await make(sessions, "mine", { owner_user_id: 1 });
    await make(sessions, "theirs", { owner_user_id: 2 });
    await make(sessions, "nobody");
    await make(sessions, "agent", { kind: "agent" });
    await sessions.update("theirs", { pinned: 1 });

    assert.deepEqual((await sessions.list()).map((s) => s.id).slice(0, 1), ["theirs"]);
    assert.deepEqual((await sessions.list()).map((s) => s.id).sort(), ["mine", "nobody", "theirs"]);
    assert.deepEqual((await sessions.list(1)).map((s) => s.id).sort(), ["mine"]);
    await make(sessions, "agent1", { kind: "agent", owner_user_id: 1 });
    assert.deepEqual((await sessions.listOwnedBy(1)).map((s) => s.id).sort(), ["agent1", "mine"]);
    assert.deepEqual(await sessions.listOwnedBy(9), []);
  });

  test("sessions: the agent list is the agent sessions only", async (t) => {
    const { sessions } = await fresh(t);
    await make(sessions, "a1", { kind: "agent", owner_user_id: 1 });
    await make(sessions, "a2", { kind: "agent", owner_user_id: 2 });
    await make(sessions, "task", { owner_user_id: 1 });

    assert.deepEqual((await sessions.listAgent()).map((s) => s.id).sort(), ["a1", "a2"]);
  });

  test("sessions: an id belongs to one session", async (t) => {
    const { sessions } = await fresh(t);
    await make(sessions, "s1");
    await assert.rejects(make(sessions, "s1", { title: "Again" }));
    assert.equal((await sessions.get("s1")).title, "Session s1");
  });

  test("sessions: update changes only the fields it is given; an empty patch changes nothing", async (t) => {
    const { sessions } = await fresh(t);
    await make(sessions, "s1");
    await sessions.update("s1", { title: "Renamed", status: "running", model: "m1" });
    await sessions.update("s1", {});
    const row = await sessions.get("s1");
    assert.deepEqual([row.title, row.status, row.model, row.provider, row.workspace], ["Renamed", "running", "m1", null, "/work"]);
  });

  test("sessions: update never changes the immutable owner or workspace from arbitrary fields", async (t) => {
    const { sessions } = await fresh(t);
    await make(sessions, "private", { owner_user_id: 7 });
    await sessions.update("private", { owner_user_id: 8, workspace: "/other", executor: "container" });
    const row = await sessions.get("private");
    assert.deepEqual([row.owner_user_id, row.workspace, row.executor], [7, "/work", "host"]);
  });

  test("sessions: browser and staff framing are set on their own", async (t) => {
    const { sessions } = await fresh(t);
    await make(sessions, "s1");
    await make(sessions, "s2");
    await sessions.setBrowser("s1", true);
    await sessions.markStaffFramingSent("s1");
    const row = await sessions.get("s1");
    assert.deepEqual([row.browser, row.staff_framing_sent], [1, 1]);

    assert.deepEqual((await sessions.listBrowserEnabled()).map((s) => s.id), ["s1"]);
    await sessions.setBrowser("s1", false);
    assert.deepEqual(await sessions.listBrowserEnabled(), []);
  });

  test("sessions: deleting one takes its events, notes and canvases and leaves the others", async (t) => {
    const { sessions, canvases } = await fresh(t);
    await make(sessions, "s1");
    await make(sessions, "s2");
    await sessions.appendEvent("s1", "text", { a: 1 });
    await sessions.appendEvent("s2", "text", { b: 2 });
    await sessions.addNote("s1", "pending");
    const canvas = { id: "c1", session_id: "s1", kind: "markdown", title: "T", content: "", revision: 0, status: "saved", active_call: null, updated_at: "2026-01-01T00:00:00.000Z" };
    await canvases.insert(canvas);

    await sessions.delete("s1");
    assert.equal(await sessions.get("s1"), undefined);
    assert.deepEqual(await sessions.eventsSince("s1"), []);
    assert.deepEqual(await sessions.takeNotes("s1"), []);
    assert.deepEqual(await canvases.list("s1"), []);
    assert.equal((await sessions.eventsSince("s2")).length, 1);
    assert.ok(await sessions.get("s2"));
  });

  test("sessions: a session left running at boot is marked interrupted, and only those", async (t) => {
    const { sessions } = await fresh(t);
    await make(sessions, "run1");
    await make(sessions, "run2");
    await make(sessions, "idle");
    await sessions.update("run1", { status: "running" });
    await sessions.update("run2", { status: "running" });

    assert.equal(await sessions.markOrphanedInterrupted(), 2);
    assert.equal((await sessions.get("run1")).status, "interrupted");
    assert.equal((await sessions.get("idle")).status, "idle");
    assert.equal(await sessions.markOrphanedInterrupted(), 0);
  });

  test("events: appended in order with a shared sequence, paged forwards and backwards within a session", async (t) => {
    const { sessions } = await fresh(t);
    await make(sessions, "s1");
    await make(sessions, "s2");
    const first = await sessions.appendEvent("s1", "text", { n: 1 });
    await sessions.appendEvent("s2", "text", { other: true });
    for (let n = 2; n <= 5; n++) await sessions.appendEvent("s1", "text", { n });

    assert.equal(first.session_id, "s1");
    assert.equal(first.type, "text");
    assert.equal(first.payload, JSON.stringify({ n: 1 }));
    assert.ok(first.seq > 0);

    const all = await sessions.eventsSince("s1");
    assert.deepEqual(all.map((e) => JSON.parse(e.payload).n), [1, 2, 3, 4, 5]);
    assert.deepEqual((await sessions.eventsSince("s1", all[1].seq, 2)).map((e) => JSON.parse(e.payload).n), [3, 4]);
    assert.deepEqual((await sessions.eventsBefore("s1", all[4].seq, 2)).map((e) => JSON.parse(e.payload).n), [3, 4]);
    assert.deepEqual((await sessions.eventsBefore("s1", all[4].seq)).map((e) => JSON.parse(e.payload).n), [1, 2, 3, 4]);
  });

  test("events: a sequence number is never reused, even after the newest event's session is deleted", async (t) => {
    const { sessions } = await fresh(t);
    await make(sessions, "s1");
    await make(sessions, "s2");
    await sessions.appendEvent("s1", "text", {});
    const last = await sessions.appendEvent("s2", "text", {});
    await sessions.delete("s2");
    const next = await sessions.appendEvent("s1", "text", {});
    assert.ok(next.seq > last.seq);
  });

  test("events: replay starts so a session gets its own last N, however busy the others were", async (t) => {
    const { sessions } = await fresh(t);
    await make(sessions, "s1");
    await make(sessions, "s2");
    for (let n = 1; n <= 4; n++) {
      await sessions.appendEvent("s1", "text", { n });
      await sessions.appendEvent("s2", "text", { n });
    }
    const start = await sessions.replayStart("s1", 2);
    const replay = await sessions.eventsSince("s1", start - 1);
    assert.deepEqual(replay.map((e) => JSON.parse(e.payload).n), [2, 3, 4]);
    assert.equal(await sessions.replayStart("s1", 10), 0);
  });

  test("events: pruned by age, across sessions, counting what went and keeping what is newer than the cutoff", async (t) => {
    const { sessions } = await fresh(t);
    await make(sessions, "s1");
    await make(sessions, "s2");
    await sessions.appendEvent("s1", "text", { n: 1 });
    await sessions.appendEvent("s2", "text", { n: 2 });

    const hourAgo = new Date(Date.now() - 3_600_000);
    assert.equal(await sessions.pruneEvents(hourAgo), 0);
    assert.equal((await sessions.eventsSince("s1")).length + (await sessions.eventsSince("s2")).length, 2);

    const inAnHour = new Date(Date.now() + 3_600_000);
    assert.equal(await sessions.pruneEvents(inAnHour), 2);
    assert.deepEqual(await sessions.eventsSince("s1"), []);
    assert.ok(await sessions.get("s1"));
  });

  test("notes: taken once, oldest first; deliveries are kept apart from what the conversation reads", async (t) => {
    const { sessions } = await fresh(t);
    await make(sessions, "s1");
    await sessions.addNote("s1", "report one");
    await sessions.addNote("s1", "unseen", true);
    await sessions.addNote("s1", "report two");

    assert.deepEqual(await sessions.takeDeliveries("s1"), ["unseen"]);
    assert.deepEqual(await sessions.takeDeliveries("s1"), []);
    assert.deepEqual(await sessions.takeNotes("s1"), ["report one", "unseen", "report two"]);
    assert.deepEqual(await sessions.takeNotes("s1"), []);
    assert.deepEqual(await sessions.takeNotes("s2"), []);
  });

  test("sessions: events and notes hang off a session that exists", async (t) => {
    const { sessions } = await fresh(t);
    await assert.rejects(sessions.appendEvent("nope", "text", {}));
    await assert.rejects(sessions.addNote("nope", "hello"));
    await make(sessions, "s1");
  });

  test("sessions: changing one that does not exist changes nothing and is not an error", async (t) => {
    const { sessions } = await fresh(t);
    await sessions.update("nope", { title: "x" });
    await sessions.setBrowser("nope", true);
    await sessions.delete("nope");
    assert.equal(await sessions.get("nope"), undefined);
  });
}
