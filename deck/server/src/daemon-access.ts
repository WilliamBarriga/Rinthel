import { fetchDaemonClient, type DaemonClient } from "./daemon-client.js";

/**
 * The only place that reads where the daemon is (`RINTHEL_DAEMON_URL`) and
 * the shared service secret (`RINTHEL_SERVICE_SECRET`). Called once, by
 * whoever composes the server; everything else is handed the `DaemonClient`.
 */
export function daemonFromEnv(): DaemonClient {
  return fetchDaemonClient({
    url: process.env.RINTHEL_DAEMON_URL || "http://127.0.0.1:8765",
    serviceSecret: serviceSecretFromEnv(),
  });
}

/** The shared service secret, empty when unset: what Node sends the daemon and what it accepts from it. */
export function serviceSecretFromEnv(): string {
  return process.env.RINTHEL_SERVICE_SECRET || "";
}
