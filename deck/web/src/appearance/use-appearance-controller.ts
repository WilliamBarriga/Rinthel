import { useCallback, useReducer, useRef } from "react";
import type { Branding, Personalization, Preferences } from "@deck/contract";
import { sharedPaletteOf, sharedPreferenceKeys, defaultBranding, defaultPreferences, effectivePersonalization, personalPreferenceKeys, storedPersonalization } from "../../../shared/appearance.mjs";
import { useReportFailure } from "../failure-context";
import { useAppearanceApi } from "../ports/context";
import { useRemote } from "../use-remote";
import { appearanceReducer } from "./model/appearance";

function personalPatch(patch: Partial<Preferences>): Partial<Preferences> {
  return Object.fromEntries(personalPreferenceKeys.filter(key => key in patch).map(key => [key, patch[key]]));
}
function paletteFromPreferences(preferences: Preferences) {
  return sharedPaletteOf(Object.fromEntries(sharedPreferenceKeys.map(key => [key, preferences[key]])));
}

const fresh = (): Personalization => ({ version: 1, preferences: { ...defaultPreferences }, profiles: [] });
export function useAppearanceController(isAdmin: boolean) {
  const api = useAppearanceApi(); const reportFailure = useReportFailure();
  const [state, dispatch] = useReducer(appearanceReducer, undefined, () => ({
    saved: fresh(), draft: fresh(), brand: { ...defaultBranding }, savedBrand: { ...defaultBranding }, loading: true, readReady: false, busy: false, error: "", notice: "",
  }));
  // Also block duplicate effects before React has rendered the started event.
  const inFlight = useRef(false);
  // The reducer takes the answer in the same tick the read ends, so the panel never shows a stale draft.
  // The role only shapes how the answer is shown (`effective` below re-applies it on every render),
  // so a role change must not start a second read: its `loaded` would overwrite the draft being edited.
  const roleAtRead = useRef(isAdmin); roleAtRead.current = isAdmin;
  const read = useCallback(async () => {
    try {
      const value = await api.appearance();
      dispatch({ type: "loaded", personal: effectivePersonalization(value.personal ?? fresh(), value.branding, roleAtRead.current)!, branding: value.branding });
    } catch (e) { dispatch({ type: "read-failed" }); throw e; }
  }, [api]);
  useRemote(read, { onFailure: reportFailure });
  async function perform(action: () => Promise<void>) {
    if (state.loading || !state.readReady || inFlight.current) return;
    inFlight.current = true; dispatch({ type: "started" });
    try { await action(); } catch (e) { reportFailure(e); dispatch({ type: "save-failed" }); }
    finally { inFlight.current = false; dispatch({ type: "finished" }); }
  }
  function storeProfiles(profiles: Personalization["profiles"]) {
    // Profile management never commits the unrelated preference preview.
    return perform(async () => dispatch({ type: "profiles-saved", personal: await api.saveAppearance(effectivePersonalization({ ...state.saved, profiles }, state.savedBrand, isAdmin)!) }));
  }
  const effective = effectivePersonalization(state.draft, state.brand, isAdmin)!;
  const personalConfig = JSON.stringify(JSON.parse(storedPersonalization(effective, false)), null, 2);
  function changePalette(patch: Partial<Preferences>) {
    if (!isAdmin || !state.readReady || state.busy) return;
    dispatch({ type: "brand-changed", patch: { palette: paletteFromPreferences({ ...effective.preferences, ...patch }) } });
  }
  return {
    preferencesDirty: personalPreferenceKeys.some(key => state.draft.preferences[key] !== state.saved.preferences[key]),
    brandingDirty: JSON.stringify(state.brand) !== JSON.stringify(state.savedBrand),
    personalConfig,
    copyPersonal: async () => {
      if (state.loading || !state.readReady) return;
      try { await navigator.clipboard.writeText(personalConfig); dispatch({ type: "copied" }); }
      catch { dispatch({ type: "copy-failed" }); }
    },
    preferences: effective.preferences, branding: state.brand, profiles: effective.profiles,
    loading: state.loading, readReady: state.readReady, error: state.error, notice: state.notice, busy: state.busy, isAdmin,
    change: (patch: Partial<Preferences>) => dispatch({ type: "preferences-changed", patch: personalPatch(patch) }),
    setTheme: (theme: Preferences["theme"]) => changePalette({ theme, paletteMode: "theme" }),
    changePalette,
    shareCurrentPalette: () => changePalette({}),
    changeBrand: (patch: Partial<Branding>) => { if (isAdmin) dispatch({ type: "brand-changed", patch }); },
    apply: () => perform(async () => dispatch({ type: "personal-saved", personal: await api.saveAppearance(effectivePersonalization(state.draft, state.savedBrand, isAdmin)!) })),
    undo: () => dispatch({ type: "undo" }),
    reset: () => dispatch({ type: "preview", preferences: personalPatch(defaultPreferences), notice: "Valores de fábrica en vista previa. Aplica para guardarlos." }),
    applyBrand: () => isAdmin ? perform(async () => dispatch({ type: "brand-saved", branding: await api.saveBranding(state.brand) })) : Promise.resolve(),
    undoBrand: () => dispatch({ type: "brand-preview", branding: state.savedBrand }),
    resetBrand: () => { if (isAdmin) dispatch({ type: "brand-preview", branding: { ...defaultBranding, palette: paletteFromPreferences(defaultPreferences) } }); },
    saveProfile: (name: string) => {
      name = name.trim();
      if (!name || name.length > 60 || (state.draft.profiles.length >= 10 && !state.draft.profiles.some(p => p.name === name))) { dispatch({ type: "invalid-profile" }); return Promise.resolve(); }
      return storeProfiles([...state.draft.profiles.filter(p => p.name !== name), { name, preferences: { ...state.draft.preferences } }]);
    },
    removeProfile: (name: string) => storeProfiles(state.draft.profiles.filter(p => p.name !== name)),
  };
}
