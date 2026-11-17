import { createHash } from "node:crypto";
import type { SlotStore } from "./slot-store.js";

/**
 * Each Session's slot of the local LLM: before every call its saved slot is restored and, if the call
 * ends well, saved again. Switching between Sessions, or coming back to one after llama-server
 * restarted, then does not prefill the whole history again. Saved slots have a byte budget: past it,
 * the least recently used go.
 *
 * llama-server has one slot for the Instance, so the slot is held from the restore to the save, one
 * HTTP request at a time. Per request and not per agent turn: a subagent shares its parent's Session
 * (and its slot) and calls in the middle of the parent's turn; holding the slot for the whole turn
 * would make the child wait for its parent forever.
 *
 * A cache that fails never fails the call: it prefills from scratch instead.
 */

/** Where a call's slot lives: the llama-server that serves it, and the slot's name. */
export interface SlotRef {
  llama: string;
  name: string;
}

/** A call that holds the slot. `end` saves when `completed` and always lets the slot go; a second `end` does nothing. */
export interface SlotTurn {
  end(completed: boolean): Promise<void>;
}

const hash = (text: string) => createHash("sha256").update(text).digest("hex");

/** The part of a slot's name every model of the Session shares, so forgetting the Session finds them all. */
const sessionKey = (ownerUserId: number, sessionId: string) => hash(`${ownerUserId}\0${sessionId}`).slice(0, 40);

/**
 * The name of a Session's slot for a model: the same Session id of another owner, or another model,
 * is another slot. Hashed, so no id the caller sends reaches the directory.
 */
export function slotName(ownerUserId: number, model: string, sessionId: string): string {
  return `${sessionKey(ownerUserId, sessionId)}-${hash(model).slice(0, 16)}`;
}

export class SessionSlots {
  /** The tail of the queue for the slot. */
  private held: Promise<void> = Promise.resolve();

  constructor(
    private readonly store: SlotStore,
    private readonly options: { maxBytes: number; warn?: (message: string) => void },
  ) {}

  /**
   * Waits for the slot, restores `slot` into it and returns the call's hold. Without `slot` (nothing to
   * name it by) the call still holds the slot, but nothing is restored or saved.
   */
  async begin(slot: SlotRef | null): Promise<SlotTurn> {
    const release = await this.acquire();
    if (slot) await this.quietly(() => this.store.restore(slot.llama, slot.name), "restore", slot.name);
    let ended = false;
    return {
      end: async (completed) => {
        if (ended) return;
        ended = true;
        try {
          if (completed && slot) {
            await this.quietly(() => this.store.save(slot.llama, slot.name), "save", slot.name);
            await this.quietly(() => this.fit(slot.name), "trim", slot.name);
          }
        } finally {
          release();
        }
      },
    };
  }

  /** Deletes every saved slot of the Session, of any model. Waits for the call in course, which may be saving one. */
  async forget(ownerUserId: number, sessionId: string): Promise<void> {
    const release = await this.acquire();
    try {
      const prefix = `${sessionKey(ownerUserId, sessionId)}-`;
      for (const slot of await this.store.saved()) if (slot.name.startsWith(prefix)) await this.store.delete(slot.name);
    } finally {
      release();
    }
  }

  /** Resolves once no call holds the slot: the save of a call whose stream pi already read lands after it. */
  async idle(): Promise<void> {
    (await this.acquire())();
  }

  private async acquire(): Promise<() => void> {
    let release!: () => void;
    const mine = new Promise<void>((resolve) => { release = resolve; });
    const before = this.held;
    this.held = before.then(() => mine);
    await before;
    return release;
  }

  /** Deletes the least recently used slots until the rest fit `maxBytes`. `kept`, the one just saved, stays even if alone it does not fit. */
  private async fit(kept: string): Promise<void> {
    const slots = (await this.store.saved()).sort((a, b) => a.usedAt - b.usedAt);
    let total = slots.reduce((sum, slot) => sum + slot.size, 0);
    for (const slot of slots) {
      if (total <= this.options.maxBytes) break;
      if (slot.name === kept) continue;
      await this.store.delete(slot.name);
      total -= slot.size;
    }
  }

  private async quietly(action: () => Promise<unknown>, what: string, name: string): Promise<void> {
    try {
      await action();
    } catch (e) {
      (this.options.warn ?? console.warn)(`[slots] ${what} ${name}: ${(e as Error).message}`);
    }
  }
}
