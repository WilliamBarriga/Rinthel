import { after, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { InMemorySlotStore, type SlotStore } from '../server/src/session-slots/slot-store.ts';
import { LlamaSlotStore } from '../server/src/session-slots/llama-slot-store.ts';
import { fakeLlama } from './helpers/fake-llama.mts';

/**
 * The `SlotStore` contract: what `SessionSlots` relies on, run against the double and against the
 * real adapter over a fake llama-server that writes its slots where `--slot-save-path` says.
 */
function slotStoreContract(name: string, open: () => Promise<{ store: SlotStore; llama: string }>) {
  describe(`SlotStore: ${name}`, () => {
    test('a saved slot restores; one never saved does not', async () => {
      const { store, llama } = await open();
      await store.save(llama, 'a');
      assert.equal(await store.restore(llama, 'a'), true);
      assert.equal(await store.restore(llama, 'b'), false);
    });

    test('saved lists each slot once, with its size, the last saved the most recent', async () => {
      const { store, llama } = await open();
      await store.save(llama, 'a');
      await store.save(llama, 'b');
      await store.save(llama, 'a');
      const saved = await store.saved();
      assert.deepEqual(saved.map((s) => s.name).sort(), ['a', 'b']);
      assert.ok(saved.every((s) => s.size > 0));
      const [older, newer] = [...saved].sort((x, y) => x.usedAt - y.usedAt);
      assert.deepEqual([older.name, newer.name], ['b', 'a']);
    });

    test('delete removes a slot, and deleting one that is not there is fine', async () => {
      const { store, llama } = await open();
      await store.save(llama, 'a');
      await store.delete('a');
      await store.delete('never');
      assert.deepEqual(await store.saved(), []);
      assert.equal(await store.restore(llama, 'a'), false);
    });
  });
}

slotStoreContract('in memory', async () => ({ store: new InMemorySlotStore(), llama: 'http://llama' }));

const roots: string[] = [];
const llamas: { close(): Promise<void> }[] = [];
after(async () => {
  for (const l of llamas) await l.close();
  for (const r of roots) rmSync(r, { recursive: true, force: true });
});
slotStoreContract('llama-server', async () => {
  const dir = mkdtempSync(path.join(tmpdir(), 'deck-slots-'));
  roots.push(dir);
  const llama = await fakeLlama(dir);
  llamas.push(llama);
  return { store: new LlamaSlotStore(dir), llama: llama.url };
});

test('an unreachable llama-server is a SlotStoreError, not a crash', async () => {
  const dir = mkdtempSync(path.join(tmpdir(), 'deck-slots-'));
  roots.push(dir);
  const store = new LlamaSlotStore(dir);
  await assert.rejects(store.restore('http://127.0.0.1:9', 'a'), { name: 'SlotStoreError' });
  await assert.rejects(store.save('http://127.0.0.1:9', 'a'), { name: 'SlotStoreError' });
});
