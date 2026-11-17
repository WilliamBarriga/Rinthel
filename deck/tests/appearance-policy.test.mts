import { test } from "node:test";
import assert from "node:assert/strict";
import { appearanceSettings } from "../server/src/appearance.ts";
import { createMemoryStore } from "../server/src/store/memory/index.ts";
import { defaultPreferences, defaultBranding, sharedPaletteOf } from "../shared/appearance.mjs";

const config = { version: 1, preferences: { ...defaultPreferences, layout: "operation", fontSize: 18 }, profiles: [{ name: "Lectura", preferences: { ...defaultPreferences, contrast: true, density: "compact" } }] };
const palette = sharedPaletteOf({ theme: "dark", paletteMode: "custom", paletteAccent: "#bb3344", paletteBackground: "#101020", paletteSurface: "#202030", paletteNavigation: "#151525", transparency: 10, tone: "cool" });

test("legacy member colors are ignored without rewriting the old document or another user's preferences", async () => {
  const store = createMemoryStore(); const appearance = appearanceSettings(store.settings);
  const legacy = JSON.stringify({ ...config, preferences: { ...config.preferences, theme: "cyberpunk", paletteAccent: "#ff00ff" }, profiles: [{ name: "Viejo", preferences: { ...defaultPreferences, paletteMode: "custom", paletteBackground: "#ff0000" } }] });
  await store.settings.set("appearance:user:2", legacy);
  await appearance.save(3, { ...config, preferences: { ...defaultPreferences, fontSize: 16 } });
  const other = (await store.settings.all())["appearance:user:3"];
  const read = await appearance.read(2);
  assert.equal(read.personal?.preferences.theme, "system");
  assert.equal(read.personal?.preferences.paletteAccent, "#5046d8");
  assert.equal(read.personal?.profiles[0].preferences.paletteBackground, "#121316");
  assert.equal(read.personal?.preferences.fontSize, 18);
  assert.equal((await store.settings.all())["appearance:user:2"], legacy);
  await appearance.save(2, read.personal);
  const stored = JSON.parse((await store.settings.all())["appearance:user:2"]);
  assert.equal(Object.hasOwn(stored.preferences, "theme"), false);
  assert.equal(Object.hasOwn(stored.profiles[0].preferences, "paletteAccent"), false);
  assert.equal((await store.settings.all())["appearance:user:3"], other);
});

test("an explicit shared palette overrides legacy personal colors and profiles for both roles", async () => {
  const appearance = appearanceSettings(createMemoryStore().settings);
  await appearance.save(1, { ...config, preferences: { ...config.preferences, theme: "light" } }, true);
  await appearance.brand({ ...defaultBranding, palette }, true);
  for (const admin of [true, false]) {
    const personal = (await appearance.read(1, admin)).personal!;
    assert.equal(personal.preferences.theme, "dark");
    assert.equal(personal.preferences.paletteAccent, "#bb3344");
    assert.equal(personal.preferences.layout, "operation");
    assert.equal(personal.profiles[0].preferences.paletteBackground, "#101020");
    assert.equal(personal.profiles[0].preferences.contrast, true);
  }
  assert.equal((await appearance.read(99)).personal?.preferences.paletteAccent, "#bb3344");
});

test("member personal writes retain accessibility and reject alternate colors in active preferences and profiles atomically", async () => {
  const store = createMemoryStore(); const appearance = appearanceSettings(store.settings);
  await appearance.save(2, config);
  const before = await store.settings.all();
  for (const value of [
    { ...config, preferences: { ...config.preferences, theme: "dark" } },
    { ...config, profiles: [{ name: "Importado", preferences: { ...defaultPreferences, paletteAccent: "#ff0000" } }] },
  ]) {
    await assert.rejects(() => appearance.save(2, value), /colores y el tema/);
    assert.deepEqual(await store.settings.all(), before);
  }
  await assert.rejects(() => appearance.brand({ ...defaultBranding, palette }), /Solo el administrador/);
  assert.equal((await appearance.read(2)).personal?.profiles[0].preferences.contrast, true);
});

test("a brand update without palette keeps the stored shared palette", async () => {
  const appearance = appearanceSettings(createMemoryStore().settings);
  await appearance.brand({ ...defaultBranding, palette }, true);
  const saved = await appearance.brand({ ...defaultBranding, name: "Renombrada" }, true);
  assert.deepEqual(saved.palette, palette);
  const read = await appearance.read(5);
  assert.equal(read.branding.name, "Renombrada");
  assert.deepEqual(read.branding.palette, palette);
  assert.equal(read.personal?.preferences.paletteAccent, "#bb3344");
});

test("a brand update with a new palette replaces it", async () => {
  const appearance = appearanceSettings(createMemoryStore().settings);
  await appearance.brand({ ...defaultBranding, palette }, true);
  const next = sharedPaletteOf({ ...palette, paletteAccent: "#00aa55" });
  assert.deepEqual((await appearance.brand({ ...defaultBranding, palette: next }, true)).palette, next);
});

test("members may repeat the shared colors in any letter case", async () => {
  const appearance = appearanceSettings(createMemoryStore().settings);
  await appearance.brand({ ...defaultBranding, palette }, true);
  const upper = { ...palette, paletteAccent: palette.paletteAccent.toUpperCase(), paletteBackground: palette.paletteBackground.toUpperCase() };
  const saved = await appearance.save(2, { ...config, preferences: { ...config.preferences, ...upper }, profiles: [{ name: "P", preferences: { ...defaultPreferences, ...upper } }] });
  assert.equal(saved.preferences.paletteAccent, "#bb3344");
});
