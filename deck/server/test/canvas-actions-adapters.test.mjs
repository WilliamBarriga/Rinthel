import { InMemorySessionNotes, storedSessionNotes } from "../dist/canvas-actions.js";
import { createMemoryStore } from "../dist/store/memory/index.js";
import { openSqliteStore } from "../dist/store/sqlite/index.js";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { after } from "node:test";
import { sessionNotesContract } from "./contract/canvas-actions.mjs";

// One contract for the port of the canvas actions, run on the double and on the adapter the portal
// composes, over the in-memory store and over `deck.db`.
sessionNotesContract("in-memory", async () => {
  const notes = new InMemorySessionNotes();
  return { notes, delivered: (id) => notes.notes.filter((n) => n.sessionId === id).map((n) => n.text) };
});

async function stored(store) {
  for (const id of ["s1", "s2"]) await store.sessions.create({ id, title: "t", workspace: "/w", executor: "host" });
  return { notes: storedSessionNotes(store), delivered: (id) => store.sessions.takeNotes(id) };
}

sessionNotesContract("stored (memory store)", async () => stored(createMemoryStore()));

let n = 0;
const dir = mkdtempSync(path.join(tmpdir(), "deck-notes-"));
after(() => rmSync(dir, { recursive: true, force: true }));
sessionNotesContract("stored (deck.db)", async () => stored(openSqliteStore(path.join(dir, `notes-${n++}.db`))));
