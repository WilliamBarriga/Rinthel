import type { BrowserRuntime } from "../instance-browser.js";
import { FrameKeeper } from "./frame-keeper.js";

/** A real viewer of the Instance browser arrived or left (the `/browser-ui` proxy says so); see `FrameKeeper`. */
export interface BrowserViewers {
  viewerConnected(): void;
  viewerDisconnected(): void;
}

/**
 * Keeps the Instance browser rendering when nobody has its view open. Only the container needs it:
 * a local Chrome is presented by a real desktop, and an external one is not Deck's to watch. Does
 * nothing until the container runs. `streamPort` is selkies' own websocket, reached directly at
 * `host`: the loopback when the container shares the host's network, its name on a user network.
 */
export function watchBrowserFrames(runtime: BrowserRuntime, streamPort: number, host?: string): BrowserViewers & { stop(): void } {
  const keeper = new FrameKeeper({
    port: streamPort,
    host,
    shouldRun: async () => {
      const state = await runtime.status();
      return state.mode === "docker" && state.container === "running";
    },
  });
  keeper.start();
  return {
    viewerConnected: () => keeper.viewerConnected(),
    viewerDisconnected: () => keeper.viewerDisconnected(),
    stop: () => keeper.stop(),
  };
}
