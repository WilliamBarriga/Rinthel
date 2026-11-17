import type { Timer } from "../timer";

export interface ManualTimer extends Timer {
  /** Moves the clock forward and runs, in order, what falls due (including what that schedules). */
  advance(ms: number): void;
  /** How many callbacks are waiting. */
  readonly pending: number;
}

export function manualTimer(): ManualTimer {
  let now = 0;
  let nextId = 0;
  const tasks = new Map<number, { at: number; fn: () => void }>();
  return {
    now: () => now,
    after(ms, fn) {
      const id = nextId++;
      tasks.set(id, { at: now + ms, fn });
      return () => void tasks.delete(id);
    },
    advance(ms) {
      const target = now + ms;
      for (;;) {
        const due = [...tasks.entries()].filter(([, t]) => t.at <= target).sort((a, b) => a[1].at - b[1].at || a[0] - b[0])[0];
        if (!due) break;
        tasks.delete(due[0]);
        now = Math.max(now, due[1].at);
        due[1].fn();
      }
      now = target;
    },
    get pending() {
      return tasks.size;
    },
  };
}
