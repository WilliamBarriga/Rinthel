import test from "node:test";
import assert from "node:assert/strict";
import { browserRuntimeContract } from "./contract/browser-runtime.mjs";
import { FakeDocker } from "./helpers/fake-docker.mjs";
import { fakeCdp } from "./helpers/fake-cdp.mjs";
import { InMemoryBrowserRuntime } from "../dist/instance-browser.js";
import { createBrowserRuntime } from "../dist/browser/browser-runtime.js";
import { cdpOverHttp } from "../dist/browser/cdp.js";
import { LocalChrome } from "../dist/browser/browser-local.js";

const noChrome = () => new LocalChrome({ candidates: ["/nonexistent/chrome"], profileDir: "/nonexistent/profile" });

browserRuntimeContract("in-memory runtime", async () => ({ runtime: new InMemoryBrowserRuntime() }));
browserRuntimeContract("docker runtime", async () => ({
  runtime: createBrowserRuntime({ external: false, cdp: cdpOverHttp("http://127.0.0.1:9"), docker: new FakeDocker(), local: noChrome(), volume: "deck_browser-profile" }),
}));

test("docker runtime: the container is the one validated by hand (host network, its profile volume, CDP on 9222, the login)", async () => {
  const docker = new FakeDocker({ image: false });
  const runtime = createBrowserRuntime({ external: false, cdp: cdpOverHttp("http://127.0.0.1:9"), docker, local: noChrome(), volume: "deck_browser-profile" });
  await runtime.install({ user: "agent", password: "s3cret", port: "3010", httpsPort: "3011" });
  assert.deepEqual(docker.pulls, ["lscr.io/linuxserver/chromium:latest"]);
  const { spec } = docker.containers.get("deck-browser");
  assert.equal(spec.HostConfig.NetworkMode, "host");
  assert.deepEqual(spec.HostConfig.Binds, ["deck_browser-profile:/config"]);
  assert.ok(spec.Env.includes("CHROME_CLI=--remote-debugging-port=9222"));
  assert.ok(spec.Env.includes("PASSWORD=s3cret"));
  await runtime.forgetProfile();
  assert.equal(docker.volumes.has("deck_browser-profile"), false);
});

test("docker runtime on a user network (Windows bridge): the container joins it and its CDP listens beyond its own loopback", async () => {
  const docker = new FakeDocker({ image: true });
  const runtime = createBrowserRuntime({ external: false, cdp: cdpOverHttp("http://deck-browser:9222"), docker, local: noChrome(), volume: "v", network: "rinthel-general_deck_browser" });
  await runtime.install({ user: "agent", password: "s3cret", port: "3010", httpsPort: "3011" });
  const { spec } = docker.containers.get("deck-browser");
  assert.equal(spec.HostConfig.NetworkMode, "rinthel-general_deck_browser");
  assert.ok(spec.Env.includes("CHROME_CLI=--remote-debugging-port=9222 --remote-debugging-address=0.0.0.0"));
});

test("docker runtime on the host network keeps CDP on the host loopback", async () => {
  const docker = new FakeDocker({ image: true });
  const runtime = createBrowserRuntime({ external: false, cdp: cdpOverHttp("http://127.0.0.1:9222"), docker, local: noChrome(), volume: "v", network: "host" });
  await runtime.install({ user: "agent", password: "s3cret", port: "3010", httpsPort: "3011" });
  const { spec } = docker.containers.get("deck-browser");
  assert.equal(spec.HostConfig.NetworkMode, "host");
  assert.ok(!spec.Env.some((e) => e.includes("remote-debugging-address")));
});

test("external runtime: found over its CDP endpoint, with no Docker, and never managed from Deck", async (t) => {
  const cdp = await fakeCdp();
  t.after(() => cdp.close());
  const runtime = createBrowserRuntime({ external: true, cdp: cdpOverHttp(cdp.url), docker: new FakeDocker({ available: false }), local: noChrome(), volume: "v" });
  const s = await runtime.status();
  assert.deepEqual([s.mode, s.container, s.available], ["external", "running", false]);
  for (const write of [() => runtime.start(), () => runtime.stop(), () => runtime.remove(), () => runtime.forgetProfile(), () => runtime.install({ user: "a", password: "p", port: "1", httpsPort: "2" })]) {
    await assert.rejects(write(), /managed outside Deck/);
  }
  cdp.state.up = false;
  assert.equal((await runtime.status()).container, "stopped");
});

test("local runtime: with no Docker socket and no Chrome on the machine, it says so rather than pretending", async () => {
  const runtime = createBrowserRuntime({ external: false, cdp: cdpOverHttp("http://127.0.0.1:9"), docker: new FakeDocker({ available: false }), local: noChrome(), volume: "v" });
  const s = await runtime.status();
  assert.deepEqual([s.mode, s.available, s.container], ["local", false, "unavailable"]);
  await assert.rejects(runtime.start(), /No Chrome or Chromium/);
});
