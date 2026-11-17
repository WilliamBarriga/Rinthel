import http from "node:http";
import { once } from "node:events";

/**
 * A fake CDP endpoint: the two HTTP reads Deck makes of a browser (`/json/version`, `/json/list`),
 * and nothing else. `up = false` answers 503, as a browser on its way down would not answer at all.
 */
export async function fakeCdp({ pages = [{ type: "page", title: "Inicio", url: "https://example.com/" }] } = {}) {
  const state = { up: true, pages, reads: [] };
  const server = http.createServer((req, res) => {
    state.reads.push(req.url);
    if (!state.up) return void res.writeHead(503).end();
    res.setHeader("content-type", "application/json");
    if (req.url === "/json/version") return void res.end(JSON.stringify({ Browser: "Chrome/130.0", "Protocol-Version": "1.3" }));
    if (req.url === "/json/list") return void res.end(JSON.stringify(state.pages));
    res.writeHead(404).end("{}");
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  return {
    url: `http://127.0.0.1:${server.address().port}`,
    state,
    close: () => new Promise((r) => { server.closeAllConnections(); server.close(() => r()); }),
  };
}
