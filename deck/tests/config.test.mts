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
