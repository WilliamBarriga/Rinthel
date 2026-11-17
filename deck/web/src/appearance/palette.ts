import type { Branding, Preferences } from "@deck/contract";

type Color = readonly number[];
const rgb = (hex: string): Color => [1, 3, 5].map(offset => parseInt(hex.slice(offset, offset + 2), 16));
const mix = (a: Color, b: Color, amount: number): Color => a.map((value, i) => Math.round(value * (1 - amount) + b[i] * amount));
const css = (color: Color) => color.join(" ");
function luminance(color: Color) {
  return color.map(v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; })
    .reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
}
function contrast(a: Color, b: Color) {
  const x = luminance(a), y = luminance(b);
  return (Math.max(x, y) + .05) / (Math.min(x, y) + .05);
}
const ink = (background: Color): Color => luminance(background) > .179 ? [0, 0, 0] : [255, 255, 255];
function readable(color: Color, backgrounds: readonly Color[], target: Color) {
  let result = color;
  for (let i = 0; i < 32 && backgrounds.some(background => contrast(result, background) < 4.8); i++) result = mix(result, target, .15);
  return result;
}

/** Keep the chosen hue around the workspace; reading surfaces get a quiet tint. */
function contentSurfaces(seed: Color, primary: Color, light: boolean, highContrast: boolean, panelSeed: Color = seed) {
  // Low-chroma, related surfaces: the base theme sets lightness, while chosen
  // colors supply the tint. Large areas never repeat a fully saturated swatch.
  const canvas = mix(light ? [245, 246, 250] : [21, 23, 29], seed, .18);
  const relatedPanel = mix(seed, panelSeed, .35);
  const surface = mix(light ? [255, 255, 255] : [32, 35, 44], relatedPanel, .12);
  const raised = mix(light ? [240, 242, 247] : [40, 44, 55], relatedPanel, .15);
  const foreground: Color = light ? [36, 35, 55] : [240, 240, 247];
  const backgrounds = [canvas, surface, raised];
  const muted = highContrast ? foreground : readable(light ? [98, 98, 115] : [178, 182, 198], backgrounds, foreground);
  const accent = readable(primary, backgrounds, foreground);
  return {
    "--content-canvas": css(canvas), "--content-surface": css(surface), "--content-raised": css(raised),
    "--content-fg": css(foreground), "--content-muted": css(muted),
    "--content-line": css(mix(surface, foreground, highContrast ? .6 : .2)),
    "--content-accent": css(accent), "--content-accent-ink": css(ink(accent)),
    "--content-ok": css(readable(rgb("#10b981"), backgrounds, foreground)),
    "--content-warn": css(readable(rgb("#eab308"), backgrounds, foreground)),
    "--content-danger": css(readable(rgb("#ef4444"), backgrounds, foreground)),
  };
}

/** Resolve every semantic color once; pages keep consuming the existing tokens. */
export function appearancePalette(preferences: Preferences, brand: Branding, light: boolean) {
  const custom = preferences.paletteMode === "custom";
  const personalized = (preferences.paletteMode ?? "theme") !== "theme";
  const primary = rgb(custom ? preferences.paletteAccent : brand.accent);
  const navigation = rgb(custom ? preferences.paletteNavigation : brand.secondary);
  const vars: Record<string, string> = {
    "--brand-action": css(primary), "--brand-action-ink": css(ink(primary)),
    "--brand-nav": css(navigation), "--brand-nav-ink": css(ink(navigation)),
    "--panel-alpha": String(1 - (preferences.transparency ?? 0) / 100),
    "--panel-blur": `${preferences.transparency > 0 ? 16 : 0}px`,
  };
  if (!personalized) {
    // Keep the established themes and their accents readable.
    const background = light ? .8 : .04;
    let accent = primary;
    for (let i = 0; i < 24; i++) {
      const l = luminance(accent);
      if ((Math.max(l, background) + .05) / (Math.min(l, background) + .05) >= 4.8) break;
      accent = mix(accent, light ? [0, 0, 0] : [255, 255, 255], .1);
    }
    vars["--accent"] = css(accent);
    Object.assign(vars, contentSurfaces(preferences.theme === "cyberpunk" ? [24, 8, 51] : light ? [255, 255, 255] : [27, 28, 32], primary, light, preferences.contrast));
    return { vars, navTone: brand.navTone, personalized, colorScheme: undefined };
  }
  const background = custom ? rgb(preferences.paletteBackground) : mix(light ? [248, 249, 252] : [14, 16, 22], primary, light ? .1 : .22);
  const panelSeed = custom ? rgb(preferences.paletteSurface) : mix(background, primary, .12);
  Object.assign(vars, contentSurfaces(background, primary, light, preferences.contrast, panelSeed));
  for (const role of ["canvas", "surface", "raised", "fg", "line", "accent", "ok", "warn", "danger"] as const) vars[`--${role}`] = vars[`--content-${role}`];
  Object.assign(vars, {
    "--chrome": css(navigation), "--palette-glow": css(primary),
    "--fg-muted": vars["--content-muted"], "--fg-subtle": vars["--content-muted"], "--fg-faint": vars["--content-muted"],
    "--accent-fg": vars["--content-accent-ink"],
  });
  return { vars, navTone: "solid", personalized, colorScheme: light ? "light" : "dark" };
}
