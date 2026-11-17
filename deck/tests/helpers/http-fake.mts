/**
 * What every HTTP fake of these tests shares: a server on a free loopback port that closes with its
 * open connections, and the request body read whole.
 */
import http from "node:http";
import { once } from "node:events";
import type { AddressInfo } from "node:net";

export interface Listening {
  /** `http://127.0.0.1:<port>`, no trailing slash. */
  url: string;
  /** Stops listening and drops the connections still open (a held stream included). */
  close(): Promise<void>;
}

/** Serves `handler` on 127.0.0.1, on a port the system picks. */
export async function listen(handler: http.RequestListener): Promise<Listening> {
  const server = http.createServer(handler);
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  return {
    url: `http://127.0.0.1:${(server.address() as AddressInfo).port}`,
    close: async () => {
      server.closeAllConnections();
      await new Promise<void>((r) => server.close(() => r()));
    },
  };
}

/** The whole request body, as bytes. */
export async function readBody(req: http.IncomingMessage): Promise<Buffer> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks);
}

/** The request body parsed as JSON; an empty body is `{}`. */
export async function readJson(req: http.IncomingMessage): Promise<any> {
  const raw = (await readBody(req)).toString("utf8");
  return raw ? JSON.parse(raw) : {};
}

/** Answers `body` as JSON with `status`. */
export const sendJson = (res: http.ServerResponse, status: number, body: unknown): void =>
  void res.writeHead(status, { "content-type": "application/json" }).end(JSON.stringify(body));
