import { describe, expect, it } from "vitest";
import type { InstanceSoul } from "@deck/contract";
import { fetchInstanceSoulApi } from "./adapters/fetch-instance-soul";
import { fakeInstanceSoulApi } from "./fakes/instance-soul";
import type { InstanceSoulApi } from "./instance-soul";

/** A stand-in for Deck's `/api/agent/instance-soul`, written from its rules (not the fake's code). */
function deckSoul(isAdmin: boolean): typeof fetch {
  let content: string | null = "# SOUL.md\n";
  const body = (): InstanceSoul => ({ name: "SOUL.md", exists: content !== null, content: content ?? "", editable: isAdmin });
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    if (new URL(String(input), "http://deck").pathname !== "/api/agent/instance-soul") return Response.json({ error: "No such route" }, { status: 404 });
    if (init?.method !== "PUT") return Response.json(body());
    if (!isAdmin) return Response.json({ error: "Solo el administrador puede usar la SOUL de la Instance." }, { status: 403 });
    const text = JSON.parse(String(init.body)).content;
    content = text.endsWith("\n") ? text : `${text}\n`;
    return Response.json(body());
  }) as typeof fetch;
}

function contract(name: string, open: (isAdmin: boolean) => InstanceSoulApi) {
  describe(`InstanceSoulApi: ${name}`, () => {
    it("the admin reads it, replaces it, and reads what was stored", async () => {
      const api = open(true);
      expect(await api.read()).toEqual({ name: "SOUL.md", exists: true, content: "# SOUL.md\n", editable: true });
      expect((await api.save("# Nueva")).content).toBe("# Nueva\n");
      expect((await api.read()).content).toBe("# Nueva\n");
    });

    it("a member reads the same text, read-only, and cannot replace it", async () => {
      const api = open(false);
      expect(await api.read()).toMatchObject({ content: "# SOUL.md\n", editable: false });
      await expect(api.save("mia")).rejects.toMatchObject({ kind: "http", status: 403 });
      expect((await api.read()).content).toBe("# SOUL.md\n");
    });
  });
}

contract("fake", (isAdmin) => fakeInstanceSoulApi({ isAdmin }));
contract("fetch adapter", (isAdmin) => fetchInstanceSoulApi(deckSoul(isAdmin)));
