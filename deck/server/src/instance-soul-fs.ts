import { lstatSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { withNewline, type InstanceSoul } from "./instance-soul.js";

/**
 * The Instance SOUL as a file on Deck's volume (`<data>/instance/SOUL.md`), where INSTALL seeds it.
 * A link there is never followed: it reads as nothing, and a write replaces the link itself with a
 * regular file. A write goes to a temporary file beside it and is renamed over it, so a Session that
 * loads it meanwhile reads the old file whole or the new one whole.
 */
export class FsInstanceSoul implements InstanceSoul {
  constructor(private readonly file: string) {}

  /** The file a member's Session loads (it may not exist yet). */
  get path(): string {
    return this.file;
  }

  read(): string | null {
    try {
      if (!lstatSync(this.file).isFile()) return null;
      return readFileSync(this.file, "utf8");
    } catch {
      return null;
    }
  }

  write(content: string): void {
    mkdirSync(path.dirname(this.file), { recursive: true });
    const temporary = `${this.file}.${randomUUID()}.tmp`;
    try {
      writeFileSync(temporary, withNewline(content), { mode: 0o644 });
      renameSync(temporary, this.file);
    } catch (e) {
      rmSync(temporary, { force: true });
      throw e;
    }
  }
}
