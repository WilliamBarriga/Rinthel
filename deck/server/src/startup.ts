import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { createServer as createHttpServer, type Server } from "node:http";
import { createServer as createHttpsServer } from "node:https";
import type { RequestListener } from "node:http";

/**
 * TLS when a certificate is supplied, plain HTTP otherwise.
 *
 * Optional because most deployments sit on a LAN or a tailnet and do not want
 * to think about certificates. Needed for the embedded browser, which refuses
 * to run unless every page above it is a secure context.
 */
export function loadTls(certPath: string | undefined, keyPath: string | undefined): { cert: Buffer; key: Buffer } | null {
  return certPath && keyPath && existsSync(certPath) && existsSync(keyPath)
    ? { cert: readFileSync(certPath), key: readFileSync(keyPath) }
    : null;
}

/**
 * On PATH via the image, but a volume that predates it has no such directory —
 * docker only seeds a volume that is empty, so an existing deploy would carry a
 * PATH entry pointing at nothing.
 */
export function ensureDir(dir: string): void {
  mkdirSync(dir, { recursive: true });
}

/** Starts listening on every interface and calls `onListening` once it does. */
export function serve(
  app: RequestListener,
  { port, tls }: { port: number; tls: { cert: Buffer; key: Buffer } | null },
  onListening: () => void,
): Server {
  return (tls ? createHttpsServer(tls, app) : createHttpServer(app)).listen(port, "0.0.0.0", onListening);
}

/**
 * What a stop signal does: run `stop` (running sessions, the store), close the server, and exit.
 * A server that does not close within `forceAfterMs` is exited anyway.
 */
export function gracefulShutdown({ stop, server, exit, log, forceAfterMs = 10_000 }: {
  stop: () => Promise<void>;
  server: Pick<Server, "close">;
  exit: (code: number) => void;
  log: (line: string) => void;
  forceAfterMs?: number;
}): (signal: string) => Promise<void> {
  return async (signal) => {
    log(`${signal} received — stopping`);
    await stop();
    server.close(() => exit(0));
    setTimeout(() => exit(0), forceAfterMs).unref();
  };
}
