/**
 * The Instance SOUL: the `SOUL.md` that says who the Agent is for every member of the Instance. A
 * member's Sessions load it as their SOUL (read-only for them); the admin edits it here and keeps a
 * `SOUL.md` of their own, in their Agent home, for their own Sessions. INSTALL seeds it from a
 * template, because an empty SOUL leaves the Agent without an identity.
 *
 * `FsInstanceSoul` (instance-soul-fs.ts) is the real adapter and `InMemoryInstanceSoul` the double;
 * both pass server/test/contract/instance-soul.mjs. There is no history: the file is read and written
 * whole.
 */
export interface InstanceSoul {
  /** Its content, or null while nobody defined it. */
  read(): string | null;
  /** Replaces it, stored with exactly one trailing newline. */
  write(content: string): void;
}

/** What `write` stores: the content with exactly one trailing newline. */
export const withNewline = (content: string): string => (content.endsWith("\n") ? content : `${content}\n`);

/** The most a SOUL may hold: it goes into every member's context, so it stays a page, not a library. */
export const MAX_SOUL_CHARS = 20_000;

export class InMemoryInstanceSoul implements InstanceSoul {
  constructor(private content: string | null = null) {}
  read(): string | null {
    return this.content;
  }
  write(content: string): void {
    this.content = withNewline(content);
  }
}
