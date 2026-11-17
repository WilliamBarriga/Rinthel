import { useEffect } from "react";
import { useAppearance } from "./Appearance";
import { useTheme } from "../theme";
import { appearancePalette } from "./palette";
export function AppearanceEffects() {
  const a = useAppearance(); const { resolved } = useTheme();
  const preferences = a?.preferences;
  useEffect(() => {
    if (!preferences) return;
    const root = document.documentElement;
    root.dataset.layout = preferences.layout;
    for (const key of ["density", "material", "tone", "depth", "font", "listStyle", "contrast", "reducedMotion"] as const) root.dataset[key] = String(preferences[key]);
    const vars: Record<string, string> = {
      "--nav-width": `${preferences.navWidth}px`, "--reading-width": `${({ focused: 550, balanced: 690, wide: 1000 })[preferences.readingWidth]}px`,
      "--radius-panel": `${preferences.radius}px`, "--radius-control": `${Math.min(12, preferences.radius)}px`, "--appearance-text-size": `${preferences.fontSize}px`,
      "--appearance-leading": String(preferences.lineHeight),
    };
    for (const [key, value] of Object.entries(vars)) root.style.setProperty(key, value);
    return () => {
      for (const key of ["layout", "density", "material", "tone", "depth", "font", "listStyle", "contrast", "reducedMotion"]) delete root.dataset[key];
      for (const key of Object.keys(vars)) root.style.removeProperty(key);
    };
  }, [preferences]);
  useEffect(() => {
    if (!a) return;
    const root = document.documentElement;
    const palette = appearancePalette(a.preferences, a.branding, resolved === "light");
    root.dataset.navTone = palette.navTone;
    root.dataset.palette = a.preferences.paletteMode ?? "theme";
    root.dataset.transparency = String((a.preferences.transparency ?? 0) > 0 && !a.preferences.contrast);
    if (palette.colorScheme) {
      root.dataset.paletteScheme = palette.colorScheme;
      root.style.setProperty("color-scheme", palette.colorScheme);
    }
    for (const [key, value] of Object.entries(palette.vars)) root.style.setProperty(key, value);
    return () => {
      delete root.dataset.navTone; delete root.dataset.palette; delete root.dataset.transparency; delete root.dataset.paletteScheme;
      root.style.removeProperty("color-scheme");
      for (const key of Object.keys(palette.vars)) root.style.removeProperty(key);
    };
  }, [a?.branding, a?.preferences, resolved]);
  return null;
}
