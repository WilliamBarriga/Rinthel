import http from "node:http";
import { existsSync } from "node:fs";

/**
 * Just enough of the Docker Engine API to run one container, over the socket rather than the CLI:
 * Deck's image has no docker binary, and a client library for five endpoints is a dependency to
 * upgrade forever.
 */
export interface DockerApi {
  /** Whether the socket is there at all. */
  available(): boolean;
  request<T = unknown>(method: string, path: string, body?: unknown): Promise<{ status: number; body: T }>;
  imagePresent(image: string): Promise<boolean>;
  /** A pull, reported as it goes: the image is gigabytes, and a silent request looks hung. */
  pullImage(image: string, onProgress: (line: string) => void): Promise<void>;
}

export function dockerOverSocket(socket: string): DockerApi {
  const request = <T = unknown>(method: string, path: string, body?: unknown): Promise<{ status: number; body: T }> =>
    new Promise((resolve, reject) => {
      const payload = body === undefined ? undefined : JSON.stringify(body);
      const req = http.request(
        {
          socketPath: socket,
          path,
          method,
          headers: payload ? { "content-type": "application/json", "content-length": Buffer.byteLength(payload) } : {},
        },
        (res) => {
          let raw = "";
          res.on("data", (c) => (raw += c));
          res.on("end", () => {
            let parsed: unknown = raw;
            try {
              parsed = raw ? JSON.parse(raw) : null;
            } catch {
              // Some endpoints answer with newline-delimited JSON or nothing.
            }
            resolve({ status: res.statusCode ?? 0, body: parsed as T });
          });
        },
      );
      req.on("error", reject);
      if (payload) req.write(payload);
      req.end();
    });

  return {
    available: () => existsSync(socket),
    request,
    async imagePresent(image) {
      const { status } = await request("GET", `/images/${encodeURIComponent(image)}/json`);
      return status === 200;
    },
    pullImage(image, onProgress) {
      const [name, tag = "latest"] = image.split(":");
      return new Promise((resolve, reject) => {
        const req = http.request(
          { socketPath: socket, path: `/images/create?fromImage=${encodeURIComponent(name)}&tag=${encodeURIComponent(tag)}`, method: "POST" },
          (res) => {
            if ((res.statusCode ?? 0) >= 400) {
              res.resume();
              return reject(new Error(`Pull failed with ${res.statusCode}`));
            }
            let buffer = "";
            res.on("data", (chunk) => {
              buffer += chunk;
              const lines = buffer.split("\n");
              buffer = lines.pop() ?? "";
              for (const line of lines) {
                if (!line.trim()) continue;
                try {
                  const m = JSON.parse(line) as { status?: string; progress?: string; error?: string };
                  if (m.error) return reject(new Error(m.error));
                  if (m.status) onProgress(`${m.status}${m.progress ? " " + m.progress : ""}`);
                } catch {
                  // A partial line; the next chunk completes it.
                }
              }
            });
            res.on("end", () => resolve());
          },
        );
        req.on("error", reject);
        req.end();
      });
    },
  };
}
