import { describe, expect, it } from "vitest";
import { PortError } from "./http-errors";
import type { ModelsApi } from "./models";
import { fetchModelsApi } from "./adapters/fetch-models";
import { fakeModelsApi, modelFixture, voiceFixture, type FakeModelsApi } from "./fakes/models";

type Refusal = FakeModelsApi["refuse"];

/** A stand-in for Deck's `/api/models`, written from its rules (not the fake's code). */
function deckModels(role: "admin" | "miembro", refusal: () => Refusal): typeof fetch {
  let active = "qwen-a";
  const voice: Record<string, string | null> = { stt: null, tts: null };
  const models = [modelFixture("qwen-a"), modelFixture("qwen-b", 131072), voiceFixture("whisper", "stt"), voiceFixture("pocket", "tts")];
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://deck");
    if (url.pathname === "/api/models/llm") return Response.json({ model: active, context_window: models.find((m) => m.id === active)!.context_window });
    if (role !== "admin") return Response.json({ error: "Solo el administrador puede usar el cambio de Local model." }, { status: 403 });
    if (url.pathname === "/api/models") return Response.json({ active: { llm: active, ...voice }, models });
    const refused = refusal();
    if (url.pathname === "/api/models/off") {
      const { capability } = JSON.parse(String(init?.body));
      if (capability !== "stt" && capability !== "tts") return Response.json({ error: "capability must be stt or tts" }, { status: 400 });
      if (refused) return Response.json({ error: "El daemon está ocupado", code: refused }, { status: 409 });
      voice[capability] = null;
      return Response.json({ ok: true, active: null, rolled_back: null, results: [], warnings: [] });
    }
    if (refused) return Response.json({ error: refused === "turns_in_flight" ? "Hay turnos en curso" : "El daemon está ocupado", code: refused }, { status: 409 });
    const id = JSON.parse(String(init?.body)).id;
    const capability = models.find((m) => m.id === id)!.capability!;
    if (capability === "llm") active = id;
    else voice[capability] = id;
    return Response.json({ ok: true, active: id, rolled_back: null, results: [], warnings: [] });
  }) as typeof fetch;
}

function contract(name: string, open: (role: "admin" | "miembro") => { api: ModelsApi; refuse(code: Refusal): void }) {
  describe(`ModelsApi: ${name}`, () => {
    it("everyone reads the Local model and its window; the admin switches it", async () => {
      const { api } = open("admin");
      expect(await api.active()).toEqual({ model: "qwen-a", context_window: 65536 });
      expect((await api.list()).models.map((m) => m.id)).toEqual(["qwen-a", "qwen-b", "whisper", "pocket"]);
      expect((await api.activate("qwen-b")).active).toBe("qwen-b");
      expect(await api.active()).toEqual({ model: "qwen-b", context_window: 131072 });
    });

    it("the admin turns stt and tts on with a catalog entry and off again; the llm is never off", async () => {
      const { api } = open("admin");
      await api.activate("whisper");
      await api.activate("pocket");
      expect((await api.list()).active).toEqual({ llm: "qwen-a", stt: "whisper", tts: "pocket" });
      expect((await api.off("stt")).ok).toBe(true);
      expect((await api.list()).active).toEqual({ llm: "qwen-a", stt: null, tts: "pocket" });
      await expect(api.off("llm" as "stt")).rejects.toMatchObject({ status: 400 });
      expect((await api.active()).model).toBe("qwen-a");
    });

    it("a member reads the model but cannot list nor switch", async () => {
      const { api } = open("miembro");
      expect((await api.active()).model).toBe("qwen-a");
      await expect(api.list()).rejects.toMatchObject({ status: 403 });
      await expect(api.activate("qwen-b")).rejects.toMatchObject({ status: 403 });
      await expect(api.off("tts")).rejects.toMatchObject({ status: 403 });
    });

    it("a refused switch is a 409 that says why, with its code", async () => {
      const world = open("admin");
      for (const code of ["turns_in_flight", "lifecycle_busy"] as const) {
        world.refuse(code);
        const error = await world.api.activate("qwen-b").catch((e) => e);
        expect(error).toBeInstanceOf(PortError);
        expect(error.status).toBe(409);
        expect((error.body as { code: string }).code).toBe(code);
        expect(error.message).toMatch(/turnos en curso|ocupado/);
      }
      expect((await world.api.active()).model).toBe("qwen-a");
    });
  });
}

contract("fake", (role) => {
  const api = fakeModelsApi({ role });
  return { api, refuse: (code) => { api.refuse = code; } };
});

contract("fetch adapter", (role) => {
  let refusal: Refusal = null;
  return { api: fetchModelsApi(deckModels(role, () => refusal)), refuse: (code) => { refusal = code; } };
});
