import type { DaemonClient } from "../daemon-client.js";
import type { Capability, ModelRouting, Route } from "./model-routing.js";
import type { CapabilityRoute, Routing } from "@deck/contract";

/**
 * `GET /model-provider/routing` as the service (policy `service`): one Local model per Instance, so
 * no user rides along. A Capability the daemon leaves out has no model that can run.
 */
export class DaemonModelRouting implements ModelRouting {
  constructor(private readonly daemon: DaemonClient) {}

  private async routing(): Promise<Routing> {
    let res: Response;
    try {
      res = await this.daemon.asService().fetch("/model-provider/routing");
    } catch (e) {
      throw new Error(`routing unavailable: ${(e as Error).message}`);
    }
    if (!res.ok) throw new Error(`routing unavailable: the daemon answered ${res.status}`);
    return (await res.json()) as Routing;
  }

  /** Where Understory is for Memoria, as the daemon says now; `null` when it is off. */
  async understoryUrl(): Promise<string | null> {
    return (await this.routing()).understory_url ?? null;
  }

  async read(capability: Capability): Promise<Route | null> {
    const route: CapabilityRoute | undefined = (await this.routing()).capabilities?.[capability];
    if (!route) return null;
    return {
      url: route.url.replace(/\/+$/, ""),
      model: route.model,
      contextWindow: route.context_window,
      reasoningFormat: route.reasoning_format,
    };
  }
}
