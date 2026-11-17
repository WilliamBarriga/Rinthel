import { useCallback, useState } from "react";
import { useModelsApi } from "../ports/context";
import { useRemote } from "../use-remote";
import { messageOf } from "../ports/http-errors";

/** The Local model every Session talks to now, for the composer's pill. */
export function useActiveModel() {
  const api = useModelsApi();
  const read = useCallback(() => api.active(), [api]);
  const remote = useRemote(read);
  return { model: remote.data?.model ?? null, contextWindow: remote.data?.context_window ?? null, refresh: remote.refresh };
}

/**
 * Controller of the Local model switch (admin): the catalog, and `activate`, which answers whether it
 * went through. A refusal (a `409` while turns are in course or the daemon is busy, a rollback) stays
 * on screen as `error` and is not the root's notice.
 */
export function useLocalModelSwitch({ onSwitched }: { onSwitched?: () => void } = {}) {
  const api = useModelsApi();
  const read = useCallback(() => api.list(), [api]);
  const remote = useRemote(read);
  const [error, setError] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);

  const activate = useCallback(async (id: string): Promise<boolean> => {
    setSwitching(true);
    setError(null);
    try {
      const result = await api.activate(id);
      if (!result.ok) {
        setError(result.rolled_back
          ? `El Local model nuevo no arrancó; se volvió a ${result.active ?? "el anterior"}.`
          : `El Local model nuevo no arrancó: ${result.results.map((r) => r.message).join(" — ") || "sin detalle"}`);
      }
      await remote.reload();
      onSwitched?.();
      return result.ok;
    } catch (e) {
      setError(messageOf(e));
      return false;
    } finally {
      setSwitching(false);
    }
  }, [api, remote.reload, onSwitched]);

  const activable = (remote.data?.models ?? []).filter((m) => m.capability === "llm");
  return {
    status: remote.status,
    loadError: remote.status === "error" ? messageOf(remote.error) : null,
    active: remote.data?.active.llm ?? null,
    models: activable,
    switching,
    error,
    activate,
  };
}
