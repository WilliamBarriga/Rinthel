import type { Branding, Personalization, Preferences } from "@deck/contract";
export interface AppearanceState {
  saved: Personalization;
  draft: Personalization;
  brand: Branding;
  savedBrand: Branding;
  loading: boolean;
  readReady: boolean;
  busy: boolean;
  error: string;
  notice: string;
}
export type AppearanceEvent =
  | { type: "loaded"; personal: Personalization; branding: Branding }
  | { type: "read-failed" }
  | { type: "preferences-changed"; patch: Partial<Preferences> }
  | { type: "brand-changed"; patch: Partial<Branding> }
  | { type: "preview"; preferences: Partial<Preferences>; notice: string }
  | { type: "undo" }
  | { type: "brand-preview"; branding: Branding }
  | { type: "started" }
  | { type: "save-failed" }
  | { type: "finished" }
  | { type: "personal-saved"; personal: Personalization }
  | { type: "profiles-saved"; personal: Personalization }
  | { type: "brand-saved"; branding: Branding }
  | { type: "copied" }
  | { type: "copy-failed" }
  | { type: "invalid-profile" };

// Retired layouts remain readable in stored documents. Resolve them locally;
// persistence still happens only through an explicit user action.
function supportedPreferences(preferences: Preferences): Preferences {
  return preferences.layout === "focus" ? { ...preferences, layout: "balanced" } : preferences;
}
function supportedPersonalization(personal: Personalization): Personalization {
  return { ...personal, preferences: supportedPreferences(personal.preferences), profiles: personal.profiles.map(profile => ({ ...profile, preferences: supportedPreferences(profile.preferences) })) };
}

export function appearanceReducer(state: AppearanceState, event: AppearanceEvent): AppearanceState {
  switch (event.type) {
    case "loaded": {
      const personal = supportedPersonalization(event.personal);
      return { ...state, saved: personal, draft: personal, brand: event.branding, savedBrand: event.branding, loading: false, readReady: true, error: "" };
    }
    case "read-failed": return { ...state, loading: false, readReady: false, error: "No se pudo cargar la apariencia. Recarga para reintentar; no se guardará sobre valores desconocidos." };
    case "preferences-changed": return { ...state, draft: { ...state.draft, preferences: supportedPreferences({ ...state.draft.preferences, ...event.patch }) }, notice: "" };
    case "brand-changed": return { ...state, brand: { ...state.brand, ...event.patch }, notice: "" };
    case "preview": return { ...state, draft: { ...state.draft, preferences: supportedPreferences({ ...state.draft.preferences, ...event.preferences }) }, notice: event.notice };
    case "undo": return { ...state, draft: state.saved, notice: "Vista previa deshecha." };
    case "brand-preview": return { ...state, brand: event.branding };
    case "started": return state.loading || state.busy || !state.readReady ? state : { ...state, busy: true, error: "", notice: "" };
    case "save-failed": return { ...state, error: "No se pudo guardar. Tus cambios siguen en vista previa; puedes reintentar o deshacer." };
    case "finished": return { ...state, busy: false };
    case "personal-saved": {
      const personal = supportedPersonalization(event.personal);
      return { ...state, saved: personal, draft: personal, notice: "Preferencias guardadas." };
    }
    case "profiles-saved": {
      const personal = supportedPersonalization(event.personal);
      return { ...state, saved: personal, draft: { ...state.draft, profiles: personal.profiles }, notice: "Perfiles guardados." };
    }
    case "brand-saved": return { ...state, brand: event.branding, savedBrand: event.branding, notice: "Marca de instalación guardada." };
    case "copied": return { ...state, error: "", notice: "Configuración personal copiada." };
    case "copy-failed": return { ...state, notice: "", error: "No se pudo copiar. Selecciona el texto de Configuración personal para copiarlo manualmente." };
    case "invalid-profile": return { ...state, error: "Escribe un nombre de hasta 60 caracteres. Máximo 10 perfiles." };
  }
}
