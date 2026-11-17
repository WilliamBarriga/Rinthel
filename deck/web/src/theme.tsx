import { createContext, useContext, useEffect, useSyncExternalStore } from "react";

/**
 * Light, dark, cyberpunk, or whatever the machine is set to.
 *
 * "system" is the default and a real option rather than a one-off starting
 * guess: someone whose desktop flips at sunset expects this to follow, and a
 * portal that decided once at first load would not. "cyberpunk" is a fixed
 * palette pick, so it is exempt from that — it never resolves to anything
 * else.
 */
export type Theme = "light" | "dark" | "cyberpunk" | "system";
type Resolved = Exclude<Theme, "system">;

const KEY = "rinthel.theme";
const media = () => window.matchMedia("(prefers-color-scheme: light)");

export const resolve = (theme: Theme): Resolved =>
  theme === "system" ? (media().matches ? "light" : "dark") : theme;

function apply(theme: Theme) {
  const root = document.documentElement;
  // Transitions are enabled only for the moment of the change, so the whole app
  // does not fade every time something re-renders.
  root.classList.add("theme-switching");
  root.dataset.theme = resolve(theme);
  window.setTimeout(() => root.classList.remove("theme-switching"), 200);
}

const THEMES: Theme[] = ["light", "dark", "cyberpunk", "system"];

function stored(): Theme {
  try {
    const value = localStorage.getItem(KEY);
    return THEMES.includes(value as Theme) ? (value as Theme) : "system";
  } catch {
    return fallbackTheme;
  }
}

const listeners = new Set<() => void>();
let fallbackTheme: Theme = "system";
let unpersistedTheme: Theme | undefined;
function snapshot(): Theme {
  return unpersistedTheme ?? stored();
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  const onStorage = () => listener();
  window.addEventListener("storage", onStorage);
  return () => { listeners.delete(listener); window.removeEventListener("storage", onStorage); };
}
function setTheme(theme: Theme) {
  fallbackTheme = theme;
  try {
    localStorage.setItem(KEY, theme);
    unpersistedTheme = undefined;
  } catch {
    // Reads can succeed while writes fail (quota or a read-only profile).
    unpersistedTheme = theme;
  }
  for (const listener of listeners) listener();
}

export const ThemePreferenceContext = createContext<{ theme: Theme; setTheme: (theme: Theme) => void; editable?: boolean } | null>(null);

export function useTheme() {
  const browserTheme = useSyncExternalStore(subscribe, snapshot);
  const personal = useContext(ThemePreferenceContext);
  const theme = personal?.theme ?? browserTheme;
  useEffect(() => {
    apply(theme);
    if (theme !== "system") return;
    const mq = media();
    const onChange = () => apply("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);
  return { theme, setTheme: personal?.setTheme ?? setTheme, resolved: resolve(theme), editable: personal?.editable ?? true };
}
