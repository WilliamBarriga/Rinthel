import type { InstanceSoul } from "@deck/contract";
import type { InstanceSoulApi } from "../instance-soul";
import { PortError } from "../http-errors";

export interface FakeInstanceSoulApi extends InstanceSoulApi {
  /** Makes the next call to `op` (a method name of the port) reject with `error`. */
  failNext(op: keyof InstanceSoulApi, error: Error): void;
}

const withNewline = (content: string) => (content.endsWith("\n") ? content : `${content}\n`);

/** In memory, with Deck's rule: everyone reads, only an admin (`isAdmin`) saves; anyone else is a `403`. `soul` null means nobody defined it. */
export function fakeInstanceSoulApi({ soul = "# SOUL.md\n", isAdmin = true }: { soul?: string | null; isAdmin?: boolean } = {}): FakeInstanceSoulApi {
  let content = soul === null ? null : withNewline(soul);
  const failures = new Map<keyof InstanceSoulApi, Error>();
  const check = (op: keyof InstanceSoulApi) => {
    const error = failures.get(op);
    if (error) {
      failures.delete(op);
      throw error;
    }
  };
  const body = (): InstanceSoul => ({ name: "SOUL.md", exists: content !== null, content: content ?? "", editable: isAdmin });
  return {
    async read() {
      check("read");
      return body();
    },
    async save(text) {
      check("save");
      if (!isAdmin) throw new PortError("http", 403, "Solo el administrador puede usar la SOUL de la Instance.");
      content = withNewline(text);
      return body();
    },
    failNext(op, error) {
      failures.set(op, error);
    },
  };
}
