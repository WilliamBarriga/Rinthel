import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { deckConfigFromEnv } from '../server/src/config.ts';

test('without the Panel secret Deck does not start: there is no open mode', () => {
  assert.throws(() => deckConfigFromEnv({}), /RINTHEL_PANEL_SECRET/);
});

test('deck.db lives on the data volume, in WAL unless DELETE is asked for', () => {
  const config = deckConfigFromEnv({ RINTHEL_PANEL_SECRET: 's', DATA_DIR: '/data' });
  assert.equal(config.databasePath, path.resolve('/data/deck.db'));
  assert.equal(config.journalMode, 'wal');
  assert.equal(deckConfigFromEnv({ RINTHEL_PANEL_SECRET: 's', DECK_DB_JOURNAL_MODE: 'DELETE' }).journalMode, 'delete');
  assert.throws(() => deckConfigFromEnv({ RINTHEL_PANEL_SECRET: 's', DECK_DB_JOURNAL_MODE: 'truncate' }), /wal or delete/);
});

test("Sessions, workspaces and llama-server's saved slots live on the data volume; the slot budget is in GB", () => {
  const config = deckConfigFromEnv({ RINTHEL_PANEL_SECRET: 's', DATA_DIR: '/data' });
  assert.equal(config.dataDir, path.resolve('/data'));
  assert.equal(config.workspaceRoot, path.resolve('/data/workspaces'));
  assert.equal(config.slotsDir, path.resolve('/data/llama-slots'));
  assert.equal(config.slotsMaxBytes, 20 * 1024 ** 3);
  const tuned = deckConfigFromEnv({ RINTHEL_PANEL_SECRET: 's', WORKSPACE_ROOT: '/srv/w', DECK_SLOTS_MAX_GB: '2' });
  assert.equal(tuned.workspaceRoot, path.resolve('/srv/w'));
  assert.equal(tuned.slotsMaxBytes, 2 * 1024 ** 3);
  assert.throws(() => deckConfigFromEnv({ RINTHEL_PANEL_SECRET: 's', DECK_SLOTS_MAX_GB: '0' }), /DECK_SLOTS_MAX_GB/);
});
