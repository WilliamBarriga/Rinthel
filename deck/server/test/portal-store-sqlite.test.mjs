import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { after } from "node:test";
import { openSqliteStore } from "../dist/store/sqlite/index.js";
import { canvasesContract } from "./contract/canvases.mjs";
import { sessionsContract } from "./contract/sessions.mjs";
import { settingsContract } from "./contract/settings.mjs";

// The contract suites against `deck.db` on a temporary file: no docker, never skipped.
const dir = mkdtempSync(path.join(tmpdir(), "deck-store-"));
after(() => rmSync(dir, { recursive: true, force: true }));
let n = 0;
const open = async () => openSqliteStore(path.join(dir, `deck-${n++}.db`));

settingsContract(open);
sessionsContract(open);
canvasesContract(open);
