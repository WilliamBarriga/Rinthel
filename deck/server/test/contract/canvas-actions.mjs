import test from "node:test";
import assert from "node:assert/strict";

/**
 * Contract for the `SessionNotes` port. `open` gives `{ notes, delivered(sessionId) }`:
 * the port and what reached a Session. A note only waits in the Session (`SessionNotes` has no way
 * to start a turn), so what reaches the Session is all there is to assert.
 */
export function sessionNotesContract(name, open) {
  test(`${name} notes: a note reaches its Session, in order, and no other`, async () => {
    const { notes, delivered } = await open();
    await notes.add("s1", "primera");
    await notes.add("s2", "ajena");
    await notes.add("s1", "segunda");
    assert.deepEqual(await delivered("s1"), ["primera", "segunda"]);
    assert.deepEqual(await delivered("s2"), ["ajena"]);
  });
}
