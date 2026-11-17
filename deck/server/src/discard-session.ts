import type { PortalStore } from "./store/port.js";
import type { SessionRoots } from "./session-roots.js";

/** What a discarded Session leaves behind besides its row: its saved slots of the local LLM. */
export interface SlotForgetter {
  forget(ownerUserId: number, sessionId: string): Promise<void>;
}

export interface DiscardDeps {
  store: PortalStore;
  slots: SlotForgetter;
  roots: Pick<SessionRoots, "discard">;
}

/**
 * Deletes a Session for good: its row, events, notes and canvases, its pi directory and its saved
 * slots. Whoever calls it has already stopped the Session's pi. A slot or a directory that cannot go
 * is logged, not a reason to keep a Session the user deleted; a Session that is not there is not an
 * error.
 */
export async function discardSession(session: { id: string; owner_user_id: number | null }, { store, slots, roots }: DiscardDeps): Promise<void> {
  await store.sessions.delete(session.id);
  await roots.discard(session.id).catch((e) => console.warn(`[sessions] ${session.id}: pi files not deleted: ${(e as Error).message}`));
  if (session.owner_user_id !== null) {
    await slots.forget(session.owner_user_id, session.id).catch((e) => console.warn(`[sessions] ${session.id}: slots not deleted: ${(e as Error).message}`));
  }
}
