/**
 * Entry of the Deck server for the browser specs (`fake-deck-app.mts` says what is real and what is
 * not). Playwright launches it (`playwright.config.ts`); nobody starts it by hand. One process, one
 * scenario, state in memory: restarting it resets everything.
 */
import { buildFakeDeck } from "./fake-deck-app.mts";

const PORT = Number(process.env.FAKE_DECK_PORT);
if (!PORT) throw new Error("FAKE_DECK_PORT is required: playwright.config.ts picks it");
const { app } = await buildFakeDeck();
app.listen(PORT, "127.0.0.1", () => console.log(`fake deck on ${PORT}`));
