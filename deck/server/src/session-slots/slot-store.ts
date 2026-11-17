/**
 * The local LLM's state saved by name, to take it up again on a later call. llama-server keeps one
 * slot for the whole Instance; only `SessionSlots` touches it, between HTTP requests.
 *
 * `restore` and `save` ask the llama-server at `llama` (the route's `url`, which moves with the
 * Local model); `saved` and `delete` act on the directory the saved slots live in, which llama-server
 * cannot list or delete. `LlamaSlotStore` is the real adapter and `InMemorySlotStore` the double;
 * both pass `tests/slot-store.contract.test.mts`.
 */
export interface SavedSlot {
  name: string;
  /** Bytes on disk. */
  size: number;
  /** When it was last saved, in epoch milliseconds: the least recently used goes first. */
  usedAt: number;
}

/** The store could not do what it was asked (llama-server down, a disk that refuses). */
export class SlotStoreError extends Error {
  override readonly name = "SlotStoreError";
}

export interface SlotStore {
  /** Loads `name` into the slot. `false` when there is nothing by that name or it does not fit: the call prefills from scratch. */
  restore(llama: string, name: string): Promise<boolean>;
  /** Saves the slot as `name`, over whatever was there. */
  save(llama: string, name: string): Promise<void>;
  /** Every saved slot, once each, in any order. */
  saved(): Promise<SavedSlot[]>;
  /** Deletes `name`; one that is not there is not an error. */
  delete(name: string): Promise<void>;
}

/** The double: slots of `slotBytes` each, an ordered clock, and a `log` of what reached it. */
export class InMemorySlotStore implements SlotStore {
  private slots = new Map<string, number>();
  private clock = 0;
  /** `restore x`, `save x`, `delete x`, in order. */
  readonly log: string[] = [];
  /** While set, `restore` and `save` fail like an unreachable llama-server. */
  down = false;

  constructor(private readonly slotBytes = 1) {}

  async restore(_llama: string, name: string): Promise<boolean> {
    this.log.push(`restore ${name}`);
    if (this.down) throw new SlotStoreError("llama-server does not answer");
    return this.slots.has(name);
  }

  async save(_llama: string, name: string): Promise<void> {
    this.log.push(`save ${name}`);
    if (this.down) throw new SlotStoreError("llama-server does not answer");
    this.slots.set(name, ++this.clock);
  }

  async saved(): Promise<SavedSlot[]> {
    return [...this.slots].map(([name, usedAt]) => ({ name, size: this.slotBytes, usedAt }));
  }

  async delete(name: string): Promise<void> {
    this.log.push(`delete ${name}`);
    this.slots.delete(name);
  }
}
