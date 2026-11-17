import type { ModelEntry } from "@deck/contract";
import { PortError } from "../http-errors";
import type { ModelsApi } from "../models";

export interface FakeModelsApi extends ModelsApi {
  /** While set, a switch is refused with this daemon code (`turns_in_flight`, `lifecycle_busy`). */
  refuse: "turns_in_flight" | "lifecycle_busy" | null;
  readonly activated: string[];
}

const REFUSALS = {
  turns_in_flight: "Hay turnos en curso: espera a que terminen para cambiar el Local model.",
  lifecycle_busy: "El daemon está ocupado con otra operación (arranque, parada, recarga o instalación); inténtalo en un momento.",
};

export function modelFixture(id: string, contextWindow = 65536): ModelEntry {
  return { id, name: id, capability: "llm", activable: true, problem: null, context_window: contextWindow, reasoning_format: "qwen-chat-template" };
}

/** In memory, with Deck's rules: a member is a `403` on the catalog and the switch; a refused switch a `409` with its code. */
export function fakeModelsApi({ models = [modelFixture("qwen-a"), modelFixture("qwen-b", 131072)], active = "qwen-a", role = "admin" }: {
  models?: ModelEntry[]; active?: string | null; role?: "admin" | "miembro";
} = {}): FakeModelsApi {
  let current = active;
  const activated: string[] = [];
  const admin = () => {
    if (role !== "admin") throw new PortError("http", 403, "Solo el administrador puede usar el cambio de Local model.");
  };
  const api: FakeModelsApi = {
    refuse: null,
    activated,
    async active() {
      const model = models.find((m) => m.id === current);
      return { model: model?.id ?? null, context_window: model?.context_window ?? null };
    },
    async list() {
      admin();
      return { active: { llm: current, stt: null, tts: null }, models };
    },
    async activate(id) {
      admin();
      if (api.refuse) throw new PortError("http", 409, REFUSALS[api.refuse], { error: REFUSALS[api.refuse], code: api.refuse });
      if (!models.some((m) => m.id === id)) throw new PortError("http", 404, "unknown_model");
      current = id;
      activated.push(id);
      return { ok: true, active: id, rolled_back: null, results: [], warnings: [] };
    },
  };
  return api;
}
