import type { PortalStore } from "./store/port.js";

const DAY_MS = 86_400_000;
const DEFAULT_DAYS = 90;

/** How long the event log keeps what pi emitted: `PORTAL_EVENT_RETENTION_DAYS`, 90 by default. */
export function eventRetentionDays(env: Record<string, string | undefined>): number {
  const days = Number(env.PORTAL_EVENT_RETENTION_DAYS);
  return Number.isFinite(days) && days > 0 ? days : DEFAULT_DAYS;
}

/** Deletes the events older than `days` and returns how many went. */
export function pruneOldEvents(store: PortalStore, days: number, now: Date = new Date()): Promise<number> {
  return store.sessions.pruneEvents(new Date(now.getTime() - days * DAY_MS));
}

/**
 * Prunes now and then once a day for as long as the process lives. A failure is
 * logged and tried again tomorrow: the log growing a day longer breaks nothing.
 */
export function startEventRetention(store: PortalStore, days: number): void {
  const run = () =>
    pruneOldEvents(store, days).then(
      (n) => n && console.log(`event retention: pruned ${n} events older than ${days} days`),
      (e) => console.error("event retention failed", e)
    );
  void run();
  setInterval(run, DAY_MS).unref();
}
