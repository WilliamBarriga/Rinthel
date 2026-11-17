/**
 * Where a Capability's calls go, as the daemon says (`GET /model-provider/routing`): straight to the
 * managed service at `url`, asking for `model`. Deck never picks a Local model: the Instance has one
 * per Capability, the admin changes it, and every Session follows (ADR 0008).
 *
 * `read` is live: a switch of the Local model changes the next answer. Nothing is cached here; the
 * caller decides how often to ask.
 */
export type Capability = "llm" | "stt" | "tts";

export interface Route {
  /** The managed service as Deck reaches it (`http://<host>:<port>`), without a trailing slash. */
  url: string;
  /** The Local model's id: what the Session's pi asks for. */
  model: string;
  /** Tokens the model holds: what pi plans compaction by. */
  contextWindow: number;
  /** How the model is told the thinking effort, from the closed list the daemon validates. */
  reasoningFormat: string;
}

export interface ModelRouting {
  /** `null` when the Capability has no active Local model that can run; throws when the daemon cannot be read. */
  read(capability: Capability): Promise<Route | null>;
}

/** The test double: routes set by hand, `null` for anything else. */
export class InMemoryModelRouting implements ModelRouting {
  private routes = new Map<Capability, Route>();
  /** Every `read`, in order. */
  readonly reads: Capability[] = [];
  down = false;

  set(capability: Capability, route: Route | null): void {
    if (route) this.routes.set(capability, route);
    else this.routes.delete(capability);
  }

  async read(capability: Capability): Promise<Route | null> {
    this.reads.push(capability);
    if (this.down) throw new Error("routing unavailable: the daemon does not answer");
    return this.routes.get(capability) ?? null;
  }
}
