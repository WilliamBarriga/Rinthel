/** Appearance-only configuration. Pure validation shared by adapters; no host paths or model settings. */
export interface Preferences {
  layout: "balanced" | "operation" | "focus";
  theme: "system" | "light" | "dark" | "cyberpunk";
  paletteMode: "theme" | "brand" | "custom";
  paletteAccent: string;
  paletteBackground: string;
  paletteSurface: string;
  paletteNavigation: string;
  transparency: number;
  density: "compact" | "comfortable" | "spacious";
  radius: number;
  material: "soft" | "flat";
  tone: "neutral" | "warm" | "cool";
  depth: "subtle" | "none";
  font: "system" | "humanist" | "editorial";
  fontSize: number;
  lineHeight: number;
  readingWidth: "focused" | "balanced" | "wide";
  listStyle: "list" | "separated";
  contrast: boolean;
  reducedMotion: boolean;
  navWidth: number;
}
export interface Personalization { version: 1; preferences: Preferences; profiles: { name: string; preferences: Preferences }[] }
export interface Branding {
  version: 1; name: string; tagline: string; accent: string; secondary: string;
  navTone: "neutral" | "tinted" | "solid";
  logo: boolean; logoSize: number; logoLight: string; logoDark: string;
  /** Shared palette; absent in legacy documents until the admin explicitly configures it. */
  palette?: SharedPalette;
}
export type SharedPalette = Pick<Preferences, "theme" | "paletteMode" | "paletteAccent" | "paletteBackground" | "paletteSurface" | "paletteNavigation" | "transparency" | "tone">;
export interface Appearance { personal: Personalization | null; branding: Branding }
export const defaultPreferences: Preferences = {
  paletteMode: "theme", paletteAccent: "#5046d8", paletteBackground: "#121316", paletteSurface: "#1b1c20", paletteNavigation: "#202126", transparency: 0,
  layout: "balanced", theme: "system", density: "comfortable", radius: 14, material: "soft", tone: "neutral", depth: "subtle",
  font: "system", fontSize: 14, lineHeight: 1.65, readingWidth: "balanced", listStyle: "list", contrast: false, reducedMotion: false,
  navWidth: 240,
};
export const defaultBranding: Branding = { version: 1, name: "Rinthel.Ai", tagline: "", accent: "#5046d8", secondary: "#54608c", navTone: "neutral", logo: true, logoSize: 30, logoLight: "", logoDark: "" };
const choices: Partial<Record<keyof Preferences, readonly string[]>> = {
  paletteMode: ["theme", "brand", "custom"],
  layout: ["balanced", "operation", "focus"], theme: ["system", "light", "dark", "cyberpunk"], density: ["compact", "comfortable", "spacious"],
  material: ["soft", "flat"], tone: ["neutral", "warm", "cool"], depth: ["subtle", "none"], font: ["system", "humanist", "editorial"],
  readingWidth: ["focused", "balanced", "wide"], listStyle: ["list", "separated"],
};
const ranges: Partial<Record<keyof Preferences, [number, number]>> = { radius: [0, 24], fontSize: [13, 20], lineHeight: [1.4, 2], navWidth: [180, 320], transparency: [0, 60] };
const colors: readonly (keyof Preferences)[] = ["paletteAccent", "paletteBackground", "paletteSurface", "paletteNavigation"];
export class AppearanceValidationError extends Error {}
export class AppearanceAccessError extends AppearanceValidationError {}
export const personalPreferenceKeys = ["layout", "density", "radius", "material", "depth", "font", "fontSize", "lineHeight", "readingWidth", "listStyle", "contrast", "reducedMotion", "navWidth"] as const satisfies readonly (keyof Preferences)[];
export const sharedPreferenceKeys = ["theme", "paletteMode", "paletteAccent", "paletteBackground", "paletteSurface", "paletteNavigation", "transparency", "tone"] as const satisfies readonly (keyof Preferences)[];
export function sharedPaletteOf(value: unknown): SharedPalette {
  const input = object(value); keys(input, [...sharedPreferenceKeys]);
  const preferences = preferencesOf(input);
  return Object.fromEntries(sharedPreferenceKeys.map(key => [key, preferences[key]])) as SharedPalette;
}
function paletteFor(branding: Branding): SharedPalette {
  return branding.palette ?? sharedPaletteOf(Object.fromEntries(sharedPreferenceKeys.map(key => [key, defaultPreferences[key]])));
}
/** Reading old documents never rewrites them; only authorized presentation fields survive. */
export function effectivePersonalization(personal: Personalization | null, branding: Branding, isAdmin: boolean): Personalization | null {
  if (!branding.palette && (isAdmin || personal === null)) return personal;
  const palette = paletteFor(branding);
  const config = personal ?? { version: 1, preferences: { ...defaultPreferences }, profiles: [] };
  const apply = (preferences: Preferences): Preferences => ({ ...preferences, ...palette });
  return { ...config, preferences: apply(config.preferences), profiles: config.profiles.map(profile => ({ ...profile, preferences: apply(profile.preferences) })) };
}
/** A complete legacy DTO may echo shared fields, but may not change them, including through profiles. */
export function personalForActor(value: unknown, branding: Branding, isAdmin: boolean): Personalization {
  const config = personalizationOf(value);
  if (!isAdmin) {
    const input = object(value);
    const palette = paletteFor(branding);
    const fold = (v: unknown) => typeof v === "string" ? v.toLowerCase() : v;
    for (const raw of [input.preferences, ...(input.profiles as unknown[]).map(profile => object(profile).preferences)]) {
      const row = object(raw);
      if (sharedPreferenceKeys.some(key => key in row && fold(row[key]) !== fold(palette[key]))) {
        throw new AppearanceAccessError("Los colores y el tema los administra el administrador. Conserva la apariencia compartida al guardar tus preferencias.");
      }
    }
  }
  return effectivePersonalization(config, branding, isAdmin)!;
}
/** New member documents contain only the explicit personal whitelist. */
export function storedPersonalization(personal: Personalization, isAdmin: boolean): string {
  const keep = (preferences: Preferences) => isAdmin ? preferences : Object.fromEntries(personalPreferenceKeys.map(key => [key, preferences[key]]));
  return JSON.stringify({ ...personal, preferences: keep(personal.preferences), profiles: personal.profiles.map(profile => ({ ...profile, preferences: keep(profile.preferences) })) });
}
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new AppearanceValidationError("Configuración inválida.");
  return value as Record<string, unknown>;
}
function keys(value: Record<string, unknown>, allowed: string[]) {
  if (Object.keys(value).some(key => !allowed.includes(key))) throw new AppearanceValidationError("Campo de apariencia desconocido.");
}
export function preferencesOf(value: unknown): Preferences {
  const input = object(value); keys(input, Object.keys(defaultPreferences));
  const result = { ...defaultPreferences };
  for (const key of Object.keys(defaultPreferences) as (keyof Preferences)[]) {
    if (!(key in input)) continue;
    const v = input[key]; const options = choices[key]; const range = ranges[key];
    if (colors.includes(key)) {
      if (typeof v !== "string" || !/^#[0-9a-f]{6}$/i.test(v)) throw new AppearanceValidationError(`Color inválido: ${key}.`);
      Object.assign(result, { [key]: v }); continue;
    }
    if (options ? typeof v !== "string" || !options.includes(v) : range ? typeof v !== "number" || !Number.isFinite(v) || v < range[0] || v > range[1] : typeof v !== "boolean") throw new AppearanceValidationError(`Valor inválido: ${key}.`);
    Object.assign(result, { [key]: v });
  }
  return result;
}
export function personalizationOf(value: unknown): Personalization {
  const input = object(value);
  if (input.version !== 1) throw new AppearanceValidationError("Versión de personalización no compatible.");
  keys(input, ["version", "preferences", "profiles"]);
  if (!Array.isArray(input.profiles) || input.profiles.length > 10) throw new AppearanceValidationError("Se permiten hasta 10 perfiles.");
  const names = new Set<string>();
  const profiles = input.profiles.map(value => {
    const row = object(value); keys(row, ["name", "preferences"]);
    if (typeof row.name !== "string" || !row.name.trim() || row.name.trim().length > 60 || names.has(row.name.trim())) throw new AppearanceValidationError("Nombre de perfil inválido o repetido.");
    names.add(row.name.trim()); return { name: row.name.trim(), preferences: preferencesOf(row.preferences) };
  });
  return { version: 1, preferences: preferencesOf(input.preferences), profiles };
}
export function brandingOf(value: unknown): Branding {
  const input = object(value); keys(input, [...Object.keys(defaultBranding), "palette"]);
  if (input.version !== 1) throw new AppearanceValidationError("Versión de marca no compatible.");
  const result = { ...defaultBranding, ...input };
  if (typeof result.name !== "string" || !result.name.trim() || result.name.length > 80 || typeof result.tagline !== "string" || result.tagline.length > 160) throw new AppearanceValidationError("Nombre o descripción de instalación inválidos.");
  if (![result.accent, result.secondary].every(v => typeof v === "string" && /^#[0-9a-f]{6}$/i.test(v))) throw new AppearanceValidationError("Color inválido.");
  if (!["neutral", "tinted", "solid"].includes(result.navTone) || typeof result.logo !== "boolean" || typeof result.logoSize !== "number" || !Number.isFinite(result.logoSize) || result.logoSize < 20 || result.logoSize > 64) throw new AppearanceValidationError("Marca inválida.");
  for (const logo of [result.logoLight, result.logoDark]) {
    // Only bounded embedded raster assets. No SVG scripts, remote tracking or expiring blob URLs.
    if (typeof logo !== "string" || logo.length > 350_000 || (logo !== "" && !/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(logo))) throw new AppearanceValidationError("Logo inválido: PNG, JPG o WebP de hasta 250 KB.");
  }
  for (const logo of [result.logoLight, result.logoDark]) {
    if (!logo) continue;
    const encoded = logo.split(",")[1];
    const bytes = encoded.length * 3 / 4 - (encoded.endsWith("==") ? 2 : encoded.endsWith("=") ? 1 : 0);
    if (bytes > 250_000) throw new AppearanceValidationError("Logo demasiado grande: máximo 250 KB.");
  }
  return { ...result, ...(input.palette === undefined ? {} : { palette: sharedPaletteOf(input.palette) }), name: result.name.trim() } as Branding;
}
