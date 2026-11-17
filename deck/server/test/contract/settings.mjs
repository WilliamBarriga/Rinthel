import test from "node:test";
import assert from "node:assert/strict";

/** Contract for `store.settings`: key/value settings. */
export function settingsContract(open) {
  const fresh = async (t) => {
    const store = await open();
    t.after(() => store.close());
    return store.settings;
  };

  test("settings: appearance documents remain independent of other users and global defaults", async (t) => {
    const settings = await fresh(t);
    const personal = '{"version":1,"preferences":{"layout":"focus"},"profiles":[]}';
    await settings.set("appearance:user:1", personal);
    await settings.set("appearance:user:2", '{"version":0,"layout":"operation"}');
    await settings.set("appearance:brand", '{"version":1,"name":"Equipo"}');
    await settings.set("thinkingLevel", "high");
    await settings.set("appearance:user:2", '{"version":1,"preferences":{"layout":"balanced"},"profiles":[]}');
    assert.equal((await settings.all())["appearance:user:1"], personal);
    assert.equal((await settings.all())["thinkingLevel"], "high");
    await settings.clear("appearance:user:2");
    assert.equal((await settings.all())["appearance:brand"], '{"version":1,"name":"Equipo"}');
  });

  test("settings: a stored value is read back, overwritten by a later set, and gone once cleared", async (t) => {
    const settings = await fresh(t);
    assert.deepEqual(await settings.all(), {});
    await settings.set("soundType", "chime");
    await settings.set("thinkingLevel", "high");
    await settings.set("soundType", "bell");
    assert.deepEqual(await settings.all(), { soundType: "bell", thinkingLevel: "high" });
    await settings.clear("soundType");
    assert.deepEqual(await settings.all(), { thinkingLevel: "high" });
  });
}
