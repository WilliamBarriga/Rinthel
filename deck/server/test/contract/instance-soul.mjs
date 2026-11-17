import test from "node:test";
import assert from "node:assert/strict";

/** Contract for the `InstanceSoul` port, whichever adapter keeps the file. `open` gives a fresh, empty one. */
export function instanceSoulContract(name, open) {
  test(`${name} instance soul: nobody defined it, so it reads as null`, async () => {
    assert.equal((await open()).read(), null);
  });

  test(`${name} instance soul: what is written is read back with one trailing newline`, async () => {
    const soul = await open();
    soul.write("# SOUL.md\n\nyou are the Agent");
    assert.equal(soul.read(), "# SOUL.md\n\nyou are the Agent\n");
    soul.write("already ends\n");
    assert.equal(soul.read(), "already ends\n");
  });

  test(`${name} instance soul: a write replaces the previous content whole`, async () => {
    const soul = await open();
    soul.write("a long first version\nwith two lines");
    soul.write("short");
    assert.equal(soul.read(), "short\n");
  });
}
