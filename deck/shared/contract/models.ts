/**
 * The daemon's Local models as Deck reads them, written by hand: the daemon declares the same shapes
 * in `rinthel/rinthel_tui/api/models/dtos.py`, and a change there is a change here.
 */

/** One Capability's route: straight to the managed service. */
export interface CapabilityRoute {
  url: string;
  model: string;
  context_window: number;
  reasoning_format: string;
}

/** `GET /model-provider/routing` (service): only the Capabilities with an active Local model that can run. */
export interface Routing {
  capabilities: Partial<Record<"llm" | "stt" | "tts", CapabilityRoute>>;
}

/** One catalog entry, valid or not. */
export interface ModelEntry {
  id: string;
  name: string | null;
  capability: string | null;
  activable: boolean;
  problem: string | null;
  context_window: number | null;
  reasoning_format: string | null;
}

/** `GET /models` (admin). */
export interface ModelListing {
  active: Record<string, string | null>;
  models: ModelEntry[];
}

/** `POST /models/activate` (admin). `rolled_back`: null when nothing had to be restored. */
export interface ActivateResult {
  ok: boolean;
  active: string | null;
  rolled_back: boolean | null;
  results: { service: string; ok: boolean; message: string }[];
  warnings: string[];
}

/** `GET /api/models/llm` (Deck, any user): the Local model every Session talks to now, or none. */
export interface ActiveLocalModel {
  model: string | null;
  context_window: number | null;
}
