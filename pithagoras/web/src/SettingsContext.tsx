import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { api } from "./api";

export interface SettingsData {
  settings: import("./api").GlobalSettings;
  stored: Partial<import("./api").GlobalSettings>;
  defaults: import("./api").GlobalSettings;
  compaction: import("./api").CompactionSettings;
  compactionDefaults: import("./api").CompactionSettings;
  executor: string;
  workspaceRoot: string;
  piSettingsPath: string;
}

interface SettingsContextValue {
  data: SettingsData | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  /** Partially update `stored` without a full fetch. */
  updateStored: (partial: Partial<import("./api").GlobalSettings>) => void;
}

const SettingsContext = createContext<SettingsContextValue>({
  data: null,
  loading: true,
  error: null,
  refresh: async () => {},
  updateStored: () => {},
});

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [data, setData] = useState<SettingsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const result = await api.settings();
      setData({
        settings: result.settings,
        stored: result.stored,
        defaults: result.defaults,
        compaction: result.compaction,
        compactionDefaults: result.compactionDefaults,
        executor: result.executor,
        workspaceRoot: result.workspaceRoot,
        piSettingsPath: result.piSettingsPath,
      });
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll every 5 seconds
  useEffect(() => {
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  const updateStored = useCallback((partial: Partial<import("./api").GlobalSettings>) => {
    setData((prev) =>
      prev
        ? { ...prev, stored: { ...prev.stored, ...partial } }
        : prev,
    );
  }, []);

  const value = useMemo(
    () => ({ data, loading, error, refresh, updateStored }),
    [data, loading, error, refresh, updateStored],
  );

  return (
    <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
  );
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) {
    throw new Error("useSettings must be used within a SettingsProvider");
  }
  return ctx;
}
