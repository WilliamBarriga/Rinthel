import { createMemoryStore } from "../dist/store/memory/index.js";
import { canvasesContract } from "./contract/canvases.mjs";
import { sessionsContract } from "./contract/sessions.mjs";
import { settingsContract } from "./contract/settings.mjs";

// The same adapter-agnostic contract suites as the SQLite leg, against the in-memory adapter.
const open = async (options) => createMemoryStore(options);

settingsContract(open);
sessionsContract(open);
canvasesContract(open);
