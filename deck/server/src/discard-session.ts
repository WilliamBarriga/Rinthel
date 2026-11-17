import type { PortalStore } from "./store/port.js";

/**
 * Delete a session for good: its row, events, notes and canvases. Whoever calls it has already
 * stopped the session's pi. The session's folder and the model slot it saved go with it once Deck
 * keeps them (they arrive with the chat); a session that is not there is not an error.
 */
export async function discardSession(id: string, { store }: { store: PortalStore }): Promise<void> {
  await store.sessions.delete(id);
}
