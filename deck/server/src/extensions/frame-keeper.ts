/**
 * Somebody has to be watching, or the browser stops rendering.
 *
 * The image composites with labwc and streams with selkies, and selkies stops
 * the capture loop when the last viewer disconnects. With nothing consuming
 * frames the compositor stops presenting, so Chrome gets no BeginFrames — and
 * every Playwright action that waits for an element to be "visible, enabled and
 * stable" waits for a frame that never comes. Clicking, typing, filling a form
 * and screenshotting all timed out; navigating and reading the page carried on
 * working, because those need no frames.
 *
 * So Deck watches the browser when nobody else is. The stream is
 * damage-based, so a still page costs almost nothing to encode. One keeper per
 * container, on that container's own stream websocket.
 */
export interface FrameKeeperOptions {
  /** The container's stream websocket: on the loopback when it shares the host's network (default). */
  port: number;
  /** Its host on a user network Deck shares with it (`BROWSER_HOST`, the container's name). */
  host?: string;
  /** Asked before each connection attempt; false means the container is not one to watch right now. */
  shouldRun?: () => Promise<boolean>;
  pollMs?: number;
  /** After being displaced, long enough not to fight over the display. */
  backoffMs?: number;
  /** selkies wants a moment between claiming the display and the first frame request. */
  startDelayMs?: number;
}

/**
 * Low, because these frames are thrown away. Playwright needs two consecutive
 * frames with the same bounding box, not a smooth picture.
 */
const FRAMERATE = 10;

export class FrameKeeper {
  private socket?: WebSocket;
  private viewers = 0;
  private timer?: NodeJS.Timeout;
  private backoffUntil = 0;

  constructor(private opts: FrameKeeperOptions) {}

  /**
   * A real viewer arrived or left. Only one client may own the primary display —
   * a second one takes it and the first is killed. So the keeper stands down for
   * as long as somebody is actually looking, and picks up again when they leave.
   */
  viewerConnected(): void {
    this.viewers++;
    this.disconnect();
  }

  viewerDisconnected(): void {
    this.viewers = Math.max(0, this.viewers - 1);
  }

  start(): void {
    if (this.timer) return;
    this.timer = setInterval(() => void this.tick().catch(() => {}), this.opts.pollMs ?? 15_000);
    this.timer.unref();
    void this.tick().catch(() => {});
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = undefined;
    this.disconnect();
  }

  private disconnect(): void {
    const open = this.socket;
    this.socket = undefined;
    try {
      open?.close();
    } catch {
      // Already gone.
    }
  }

  private connect(): void {
    const ws = new WebSocket(`ws://${this.opts.host ?? "127.0.0.1"}:${this.opts.port}/websocket`);
    this.socket = ws;
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      // Claiming the primary display is what makes selkies capture at all; a
      // client that never says which display it is watching is treated as a
      // bystander and the capture loop stays stopped. No resolution is sent
      // with it, so the desktop a person set up is left as it is.
      ws.send(`SETTINGS,${JSON.stringify({ displayId: "primary", framerate: FRAMERATE })}`);
      setTimeout(() => {
        if (this.socket === ws && ws.readyState === WebSocket.OPEN) ws.send("START_VIDEO");
      }, this.opts.startDelayMs ?? 500);
    };

    ws.onmessage = (event) => {
      // KILL means a real viewer took the display. Stay away for a while rather
      // than reconnecting into a fight over it.
      if (typeof event.data === "string" && event.data.startsWith("KILL")) {
        this.backoffUntil = Date.now() + (this.opts.backoffMs ?? 60_000);
        this.disconnect();
      }
    };

    ws.onclose = () => {
      if (this.socket === ws) this.socket = undefined;
    };
    ws.onerror = () => {
      if (this.socket === ws) this.socket = undefined;
    };
  }

  private async tick(): Promise<void> {
    if (this.socket) return;
    if (this.viewers > 0 || Date.now() < this.backoffUntil) return;
    if (this.opts.shouldRun && !(await this.opts.shouldRun())) return;
    try {
      this.connect();
    } catch {
      // The container may be on its way up. The next tick tries again.
    }
  }
}
