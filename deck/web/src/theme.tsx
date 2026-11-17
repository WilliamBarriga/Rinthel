import { createContext, useContext, useEffect, useState, useSyncExternalStore } from "react";

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

/**
 * The theme in effect, for the rare thing that needs the value rather than the
 * CSS variables — mermaid draws an SVG with baked-in colours, so it has to be
 * told. Read off the attribute `apply()` writes, so there is still one source
 * of truth and no second copy of the preference to keep in step.
 */
export function useResolvedTheme(): "light" | "dark" {
  const [resolved, setResolved] = useState<"light" | "dark">(
    () => ((document.documentElement.dataset.paletteScheme ?? document.documentElement.dataset.theme) === "light" ? "light" : "dark"),
  );
  useEffect(() => {
    const root = document.documentElement;
    const read = () => setResolved((root.dataset.paletteScheme ?? root.dataset.theme) === "light" ? "light" : "dark");
    const observer = new MutationObserver(read);
    observer.observe(root, { attributes: true, attributeFilter: ["data-theme", "data-palette-scheme"] });
    read();
    return () => observer.disconnect();
  }, []);
  return resolved;
}
