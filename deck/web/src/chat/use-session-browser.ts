import { useCallback, useEffect, useRef, useState } from "react";
import type { BrowserStatus } from "@deck/contract";
import { useBrowserApi } from "../ports/context";
import { clampWidth, MIN_TOOLS_WIDTH, TOOLS_WIDTH_KEY } from "./model/session-browser";

const messageOf = (e: unknown) => (e instanceof Error ? e.message : String(e));

function storedWidth(): number | null {
  try {
    const raw = Number(window.localStorage.getItem(TOOLS_WIDTH_KEY));
    return Number.isFinite(raw) && raw > 0 ? raw : null;
  } catch {
    return null;
  }
}

/**
 * Controller of a Session's browser panel (admin): the Instance browser's state, read once on mount
 * (a refused or failed read leaves `status` null, which the view reads as "no browser"), whether this
 * Session's Agent may drive it (`enabled`, from the Sessions the browser lists), and the panel itself.
 * The frame is mounted on the first open and only hidden after (`used`), so closing the panel never
 * reloads the page or drops what was typed into it. The panel's width is kept across reloads.
 */
export function useSessionBrowser(sessionId: string, { onFailure }: { onFailure?: (error: unknown) => void } = {}) {
  const api = useBrowserApi();
  const [status, setStatus] = useState<BrowserStatus | null>(null);
  const [open, setOpen] = useState(false);
  const [used, setUsed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** What the admin just asked for, shown until the browser's answer is read again. */
  const [asked, setAsked] = useState<boolean | null>(null);
  const [width, setWidth] = useState(() => storedWidth() ?? 480);
  const failure = useRef(onFailure);
  failure.current = onFailure;
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const next = await api.status();
      if (mounted.current) setStatus(next);
    } catch {
      // Not an admin, or no answer: the Session shows no browser.
      if (mounted.current) setStatus(null);
    }
  }, [api]);

  useEffect(() => {
    mounted.current = true;
    void refresh();
    return () => { mounted.current = false; };
  }, [refresh]);

  useEffect(() => {
    try { window.localStorage.setItem(TOOLS_WIDTH_KEY, String(width)); } catch { /* private mode: not kept */ }
  }, [width]);

  return {
    status,
    available: status !== null,
    running: status?.running ?? false,
    enabled: asked ?? status?.sessions.some((s) => s.id === sessionId) ?? false,
    error,
    open,
    used,
    toggleOpen() {
      setOpen((was) => !was);
      setUsed(true);
    },
    close: () => setOpen(false),
    width,
    resize: (delta: number, max: number) => setWidth((w) => clampWidth(w + delta, max)),
    minWidth: MIN_TOOLS_WIDTH,
    async setEnabled(on: boolean) {
      setError(null);
      setAsked(on);
      try {
        await api.setSessionBrowser(sessionId, on);
      } catch (e) {
        failure.current?.(e);
        if (mounted.current) setError(messageOf(e));
      }
      await refresh();
      if (mounted.current) setAsked(null);
    },
  };
}
