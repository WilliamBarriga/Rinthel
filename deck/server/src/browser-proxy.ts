import http from "node:http";
import https from "node:https";
import type { Duplex } from "node:stream";
import type { Express } from "express";
import type { BrowserSettings } from "./browser-settings.js";
import type { BrowserViewers } from "./browser/browser-frames.js";
import { claimsOfRequest } from "./identity.js";
import { adminRefusal } from "./api/admin-only.js";
import { INSTANCE_BROWSER } from "./api/browser.js";
import { IDENTITY_REFUSAL, readIdentity, type IdentityAccess, type SessionIdentity } from "./session-identity.js";

/**
 * The Instance browser's own view (KasmVNC), served through Deck at `/browser-ui`.
 *
 * A proxy rather than a link to its HTTPS port, for two reasons. The VNC client refuses to run
 * outside a secure context, and a frame is only one if every ancestor is: same-origin, it inherits
 * whatever Deck has. And it removes a second credential: Deck has already decided who you are, so it
 * holds the browser's password rather than asking for it again.
 */
export const BROWSER_UI_PREFIX = "/browser-ui";

export interface BrowserProxyDeps {
  settings: BrowserSettings;
  identity: SessionIdentity;
  /** Where the browser's view listens (`BROWSER_HOST`, loopback by default). */
  host: string;
  /** Told when somebody opens or closes the view, so the frame keeper stands down meanwhile. */
  viewers?: BrowserViewers;
}

interface Upstream {
  port: number;
  auth: string;
}

/** Where the browser is listening and the login it wants, read live from the saved config. */
async function upstreamOf(settings: BrowserSettings): Promise<Upstream> {
  const { user, password, httpsPort } = await settings.config();
  return { port: Number(httpsPort), auth: "Basic " + Buffer.from(`${user}:${password}`).toString("base64") };
}

/** Self-signed upstream on loopback: verifying it would mean pinning its own certificate. */
const agent = new https.Agent({ rejectUnauthorized: false });

/** The caller's headers minus their Deck cookies: the browser's login is the `authorization` Deck adds. */
function upstreamHeaders(req: http.IncomingMessage, host: string, target: Upstream): http.OutgoingHttpHeaders {
  const { cookie: _cookie, ...rest } = req.headers;
  return { ...rest, host: `${host}:${target.port}`, authorization: target.auth };
}

/**
 * Whether the caller may see the Instance browser: an admin by the role the Instance has now, never
 * the one in the access token, as `adminOnly` decides. Mounted outside `/api`, so `requireAuth` did
 * not run: no valid cookie is a `401`.
 */
async function access(req: http.IncomingMessage, identity: SessionIdentity): Promise<IdentityAccess> {
  const claims = claimsOfRequest(req);
  if (!claims) return 401;
  const read = await readIdentity(() => identity.current(claims.userId));
  if (read.access !== 200) return read.access;
  return read.now.role === "admin" ? 200 : 403;
}

const UPGRADE_REFUSAL = { 401: "401 Unauthorized", 403: "403 Forbidden", 502: "502 Bad Gateway" } as const;

/** The route half: mounted before the web UI, whose fallback would otherwise answer `/browser-ui` with Deck's own page. */
export function mountBrowserProxy(app: Express, deps: BrowserProxyDeps): void {
  app.use(BROWSER_UI_PREFIX, async (req, res) => {
    const allowed = await access(req, deps.identity);
    if (allowed !== 200) return void res.status(allowed).send(allowed === 403 ? adminRefusal(INSTANCE_BROWSER) : IDENTITY_REFUSAL[allowed]);
    let target: Upstream;
    try {
      target = await upstreamOf(deps.settings);
    } catch (e) {
      return void res.status(502).send(`The browser is not available: ${(e as Error).message}`);
    }
    const proxied = https.request(
      // Express strips the mount path from req.url, so it is already relative.
      { host: deps.host, port: target.port, path: req.url || "/", method: req.method, headers: upstreamHeaders(req, deps.host, target), agent },
      (upstream) => {
        res.writeHead(upstream.statusCode ?? 502, upstream.headers);
        upstream.pipe(res);
      },
    );
    proxied.on("error", (e) => {
      if (!res.headersSent) res.statusCode = 502;
      res.end(`The browser is not answering: ${e.message}`);
    });
    req.pipe(proxied);
  });
}

/** The stream half, which needs the server rather than the app: Express never sees an upgrade. */
export function attachBrowserUpgrade(server: http.Server, deps: BrowserProxyDeps): void {
  const refuse = (socket: Duplex, status: string) => socket.end(`HTTP/1.1 ${status}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n`);

  server.on("upgrade", async (req: http.IncomingMessage, socket: Duplex, head: Buffer) => {
    if (!req.url?.startsWith(BROWSER_UI_PREFIX)) return;
    try {
      const allowed = await access(req, deps.identity);
      if (allowed !== 200) return void refuse(socket, UPGRADE_REFUSAL[allowed]);
      const target = await upstreamOf(deps.settings);
      const proxied = https.request({
        host: deps.host,
        port: target.port,
        path: req.url.slice(BROWSER_UI_PREFIX.length) || "/",
        method: "GET",
        headers: upstreamHeaders(req, deps.host, target),
        agent,
      });
      proxied.end();
      proxied.on("upgrade", (upstreamRes, upstreamSocket, upstreamHead) => {
        const lines = Object.entries(upstreamRes.headers).map(([k, v]) => `${k}: ${v}`);
        socket.write(`HTTP/1.1 101 Switching Protocols\r\n${lines.join("\r\n")}\r\n\r\n`);
        if (upstreamHead?.length) socket.unshift(upstreamHead);
        if (head?.length) upstreamSocket.unshift(head);
        upstreamSocket.pipe(socket).pipe(upstreamSocket);
        // Somebody is watching now: Deck's own stream gets out of the way (one client holds the display).
        deps.viewers?.viewerConnected();
        let counted = true;
        const close = () => {
          if (counted) {
            counted = false;
            deps.viewers?.viewerDisconnected();
          }
          upstreamSocket.destroy();
          socket.destroy();
        };
        socket.on("close", close);
        upstreamSocket.on("close", close);
        socket.on("error", close);
        upstreamSocket.on("error", close);
      });
      proxied.on("error", () => socket.destroy());
    } catch {
      refuse(socket, "502 Bad Gateway");
    }
  });
}
