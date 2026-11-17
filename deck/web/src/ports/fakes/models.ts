import type { ModelEntry } from "@deck/contract";
import { PortError } from "../http-errors";
import type { ModelsApi, VoiceCapability } from "../models";

export interface FakeModelsApi extends ModelsApi {
  /** While set, a switch or a voice off is refused with this daemon code (`turns_in_flight`, `lifecycle_busy`). */
  refuse: "turns_in_flight" | "lifecycle_busy" | null;
  readonly activated: string[];
  /** Every voice Capability turned off, in order. */
  readonly turnedOff: VoiceCapability[];
}

const REFUSALS = {
  turns_in_flight: "Hay turnos en curso: espera a que terminen para cambiar el Local model.",
  lifecycle_busy: "El daemon está ocupado con otra operación (arranque, parada, recarga o instalación); inténtalo en un momento.",
};

export function modelFixture(id: string, contextWindow = 65536): ModelEntry {
  return { id, name: id, capability: "llm", activable: true, problem: null, context_window: contextWindow, reasoning_format: "qwen-chat-template" };
}

/** A voice entry of the catalog: whisper for `stt`, a TTS model for `tts`. */
export function voiceFixture(id: string, capability: VoiceCapability): ModelEntry {
  return { id, name: id, capability, activable: true, problem: null, context_window: null, reasoning_format: null };
}

/**
 * In memory, with Deck's rules: a member is a `403` on the catalog, the switch and the voice off; a
 * refused switch a `409` with its code; the `llm` is never off (`400`).
 */
export function fakeModelsApi({
  models = [modelFixture("qwen-a"), modelFixture("qwen-b", 131072), voiceFixture("whisper", "stt"), voiceFixture("pocket", "tts")],
  active = "qwen-a",
  voice = { stt: null, tts: null },
  role = "admin",
}: {
  models?: ModelEntry[]; active?: string | null; voice?: Record<VoiceCapability, string | null>; role?: "admin" | "miembro";
} = {}): FakeModelsApi {
  let current = active;
  const voiceActive = { ...voice };
  const activated: string[] = [];
  const turnedOff: VoiceCapability[] = [];
  const admin = () => {
    if (role !== "admin") throw new PortError("http", 403, "Solo el administrador puede usar el cambio de Local model.");
  };
  const refused = () => {
    if (api.refuse) throw new PortError("http", 409, REFUSALS[api.refuse], { error: REFUSALS[api.refuse], code: api.refuse });
  };
  const api: FakeModelsApi = {
    refuse: null,
    activated,
    turnedOff,
    async active() {
      const model = models.find((m) => m.id === current);
      return { model: model?.id ?? null, context_window: model?.context_window ?? null };
    },
    async list() {
      admin();
      return { active: { llm: current, ...voiceActive }, models };
    },
    async activate(id) {
      admin();
      refused();
      const model = models.find((m) => m.id === id);
      if (!model) throw new PortError("http", 404, "unknown_model");
      if (model.capability === "stt" || model.capability === "tts") voiceActive[model.capability] = id;
      else current = id;
      activated.push(id);
      return { ok: true, active: id, rolled_back: null, results: [], warnings: [] };
    },
    async off(capability) {
      admin();
      if (capability !== "stt" && capability !== "tts") throw new PortError("http", 400, "capability must be stt or tts");
      refused();
      voiceActive[capability] = null;
      turnedOff.push(capability);
      return { ok: true, active: null, rolled_back: null, results: [], warnings: [] };
    },
  };
  return api;
}
