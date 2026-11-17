import type { SessionPrincipalDto } from "@deck/contract";
import { userNotAvailable, type DaemonClient } from "./daemon-client.js";
import type { SessionIdentity } from "./session-identity.js";

/**
 * `GET /identity/me/session-principal` as the service acting for the user (`service_as_user`, the one route of the
 * daemon with that policy): the user's live role, read again on every judged request.
 */
export function daemonSessionIdentity(daemon: DaemonClient, { timeoutMs = 2_000 } = {}): SessionIdentity {
  return {
    async current(userId) {
      const res = await daemon.actingAs(userId).fetch("/identity/me/session-principal", { signal: AbortSignal.timeout(timeoutMs) });
      // The daemon answers 401 for a bad service secret and for a user who is disabled or gone; only the second is `null`.
      if (await userNotAvailable(res)) return null;
      if (!res.ok) throw new Error("La identidad no está disponible");
      const body = await res.json() as Partial<SessionPrincipalDto>;
      if (body.user_id !== userId || !["admin", "miembro"].includes(String(body.role))) throw new Error("Identidad inválida");
      return { userId, role: body.role as SessionPrincipalDto["role"] };
    },
  };
}
