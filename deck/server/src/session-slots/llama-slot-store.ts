import { readdir, stat, unlink, utimes } from "node:fs/promises";
import path from "node:path";
import { SlotStoreError, type SavedSlot, type SlotStore } from "./slot-store.js";

/** Reading or writing a whole slot on disk: seconds with a long context. */
const TIMEOUT_MS = 30_000;
const SUFFIX = ".bin";

/**
 * `SlotStore` over llama-server started with `--slot-save-path <directory>`: save and restore with
 * `POST /slots/0?action=save|restore` (the file name in the body; slot 0 is the only one with
 * `--parallel 1`), and list and delete the files of that directory, which llama-server cannot do.
 * Each slot is `<name>.bin`. API: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
 *
 * `directory` is that same path as this process sees it: Deck's volume holds it
 * (`data/deck/llama-slots` on the host, `/data/llama-slots` in the container).
 */
export class LlamaSlotStore implements SlotStore {
  /** The last `usedAt` handed out: two saves in the same millisecond still keep their order. */
  private lastUsed = 0;

  constructor(private readonly directory: string) {}

  async restore(llama: string, name: string): Promise<boolean> {
    // A 400 is no file, or one that does not fit the KV cache: the call prefills from scratch.
    const res = await this.action(llama, "restore", name);
    if (res.status !== 200) {
      await res.body?.cancel();
      return false;
    }
    const body = (await res.json().catch(() => ({}))) as { n_restored?: number };
    return (body.n_restored ?? 0) > 0;
  }

  async save(llama: string, name: string): Promise<void> {
    const res = await this.action(llama, "save", name);
    if (res.status !== 200) throw new SlotStoreError(`llama-server did not save the slot: HTTP ${res.status} ${await res.text()}`);
    await res.body?.cancel();
    // The kernel's mtime is coarse; `usedAt` is ours, strictly increasing.
    const now = Math.max(Date.now(), this.lastUsed + 1);
    this.lastUsed = now;
    await utimes(this.file(name), now / 1000, now / 1000).catch(() => {
      // Saved somewhere else than this directory: nothing to mark.
    });
  }

  async saved(): Promise<SavedSlot[]> {
    let names: string[];
    try {
      names = await readdir(this.directory);
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code === "ENOENT") return [];
      throw new SlotStoreError(`cannot list the saved slots: ${(e as Error).message}`);
    }
    const slots: SavedSlot[] = [];
    for (const file of names.filter((n) => n.endsWith(SUFFIX))) {
      try {
        const info = await stat(path.join(this.directory, file));
        if (info.isFile()) slots.push({ name: file.slice(0, -SUFFIX.length), size: info.size, usedAt: info.mtimeMs });
      } catch {
        // Deleted while listing.
      }
    }
    return slots;
  }

  async delete(name: string): Promise<void> {
    try {
      await unlink(this.file(name));
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code !== "ENOENT") throw new SlotStoreError(`cannot delete the slot ${name}: ${(e as Error).message}`);
    }
  }

  private file(name: string): string {
    return path.join(this.directory, `${name}${SUFFIX}`);
  }

  private async action(llama: string, action: "save" | "restore", name: string): Promise<Response> {
    try {
      return await fetch(`${llama}/slots/0?action=${action}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ filename: `${name}${SUFFIX}` }),
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
    } catch (e) {
      throw new SlotStoreError(`llama-server: ${(e as Error).message}`);
    }
  }
}
