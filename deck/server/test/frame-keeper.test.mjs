import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { createHash } from "node:crypto";
import { once } from "node:events";
import { FrameKeeper } from "../dist/extensions/frame-keeper.js";

/**
 * A stand-in for selkies' stream websocket: it accepts the upgrade, decodes the client's (masked,
 * short) text frames, and can send one text frame back. Enough to see what the keeper asks for.
 */
async function fakeStream(address = "127.0.0.1") {
  const state = { messages: [], sockets: [], closed: 0 };
  const server = http.createServer();
  server.on("upgrade", (req, socket) => {
    const accept = createHash("sha1").update(req.headers["sec-websocket-key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest("base64");
    socket.write(`HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`);
    state.sockets.push(socket);
    socket.on("close", () => state.closed++);
    socket.on("error", () => {});
    socket.on("data", (buf) => {
      let at = 0;
      while (at + 6 <= buf.length) {
        const opcode = buf[at] & 0x0f;
        const len = buf[at + 1] & 0x7f;
        const mask = buf.subarray(at + 2, at + 6);
        const body = Buffer.from(buf.subarray(at + 6, at + 6 + len)).map((b, i) => b ^ mask[i % 4]);
        if (opcode === 1) state.messages.push(body.toString());
        // The client closes: answer the close and hang up, as a server does.
        if (opcode === 8) socket.end(Buffer.from([0x88, 0]));
        at += 6 + len;
      }
    });
  });
  server.listen(0, address);
  await once(server, "listening");
  return {
    port: server.address().port,
    state,
    send: (text) => {
      const body = Buffer.from(text);
      for (const s of state.sockets) s.write(Buffer.concat([Buffer.from([0x81, body.length]), body]));
    },
    close: () => new Promise((r) => { for (const s of state.sockets) s.destroy(); server.close(() => r()); }),
  };
}

const until = async (check, ms = 2000) => {
  const end = Date.now() + ms;
  while (!check()) {
    if (Date.now() > end) throw new Error("timed out");
    await new Promise((r) => setTimeout(r, 10));
  }
};

test("frame keeper: with the container running and nobody watching, it claims the display and asks for video", async (t) => {
  const stream = await fakeStream();
  const keeper = new FrameKeeper({ port: stream.port, shouldRun: async () => true, startDelayMs: 10, pollMs: 50 });
  t.after(async () => { keeper.stop(); await stream.close(); });
  keeper.start();
  await until(() => stream.state.messages.includes("START_VIDEO"));
  assert.match(stream.state.messages[0], /^SETTINGS,\{"displayId":"primary","framerate":10\}$/);
});

test("frame keeper: on a user network it watches the container at its own host, not the loopback", async (t) => {
  // Another loopback address stands in for the container's name on the shared network.
  const stream = await fakeStream("127.0.0.2");
  const keeper = new FrameKeeper({ host: "127.0.0.2", port: stream.port, shouldRun: async () => true, startDelayMs: 10, pollMs: 50 });
  t.after(async () => { keeper.stop(); await stream.close(); });
  keeper.start();
  await until(() => stream.state.messages.includes("START_VIDEO"));
});

test("frame keeper: a container not to watch (stopped, local or external) is never connected to", async (t) => {
  const stream = await fakeStream();
  const keeper = new FrameKeeper({ port: stream.port, shouldRun: async () => false, pollMs: 20 });
  t.after(async () => { keeper.stop(); await stream.close(); });
  keeper.start();
  await new Promise((r) => setTimeout(r, 120));
  assert.equal(stream.state.sockets.length, 0);
});

test("frame keeper: a real viewer makes it stand down; a KILL from the stream keeps it away", async (t) => {
  const stream = await fakeStream();
  const keeper = new FrameKeeper({ port: stream.port, shouldRun: async () => true, startDelayMs: 10, pollMs: 30, backoffMs: 10_000 });
  t.after(async () => { keeper.stop(); await stream.close(); });
  keeper.start();
  await until(() => stream.state.sockets.length === 1);
  keeper.viewerConnected();
  await until(() => stream.state.closed === 1);
  await new Promise((r) => setTimeout(r, 100));
  assert.equal(stream.state.sockets.length, 1, "no reconnection while somebody watches");
  keeper.viewerDisconnected();
  await until(() => stream.state.sockets.length === 2);
  await until(() => stream.state.messages.filter((m) => m === "START_VIDEO").length >= 1);
  stream.send("KILL");
  await until(() => stream.state.closed === 2);
  await new Promise((r) => setTimeout(r, 120));
  assert.equal(stream.state.sockets.length, 2, "it backs off after being displaced");
});
