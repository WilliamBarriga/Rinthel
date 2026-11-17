/** Port: deferred work. Injected where code waits (retries, polling) so tests never patch the global timers (ADR 0007). */
export interface Timer {
  /** Runs `fn` after `ms`; the returned function cancels it. */
  after(ms: number, fn: () => void): () => void;
  /** Milliseconds on this timer's clock; only differences between two readings mean anything. */
  now(): number;
}

export const systemTimer: Timer = {
  now: () => Date.now(),
  after(ms, fn) {
    const id = setTimeout(fn, ms);
    return () => clearTimeout(id);
  },
};
