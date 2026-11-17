import { useCallback, useEffect, useRef, useState } from "react";

export interface RemoteOptions {
  /** Tells the root about a failed read, so a `401` leads to the login and a `502` to its notice. */
  onFailure?: (error: unknown) => void;
}

export type RemoteStatus = "loading" | "ready" | "error";

/**
 * The read every controller repeats: load, keep the failure, retry, and tell the root.
 * `read` must be stable (a `useCallback` over what it reads); a new one starts a new read and
 * the answer of the old one is dropped, failure included. `reload` reads again keeping the
 * last data on screen, and answers whether it went through when it ends.
 *
 * One order for everyone: a failure is reported to `onFailure` first, whether or not the
 * component is still mounted, and only then is state set. A `401` after unmount still
 * reaches the login; a superseded read reports nothing. No cache, no automatic refetch.
 */
export function useRemote<T>(read: () => Promise<T>, { onFailure }: RemoteOptions = {}) {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);
  const [status, setStatus] = useState<RemoteStatus>("loading");
  const generation = useRef(0);
  const mounted = useRef(true);
  const failure = useRef(onFailure);
  failure.current = onFailure;

  const load = useCallback(async (): Promise<boolean> => {
    const current = ++generation.current;
    try {
      const value = await read();
      if (generation.current !== current || !mounted.current) return false;
      setData(value); setError(null); setStatus("ready");
      return true;
    } catch (e) {
      if (generation.current !== current) return false;
      failure.current?.(e);
      if (!mounted.current) return false;
      setError(e); setStatus("error");
      return false;
    }
  }, [read]);

  useEffect(() => {
    mounted.current = true;
    setStatus("loading");
    void load();
    return () => { mounted.current = false; };
  }, [load]);
  const reload = useCallback(() => { setStatus(s => (s === "error" ? "loading" : s)); return load(); }, [load]);
  return { data, error, status, reload, refresh: load };
}
