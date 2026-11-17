import { defaultBranding, defaultPreferences, personalizationOf, brandingOf, effectivePersonalization, personalForActor, AppearanceAccessError } from "../../../../shared/appearance.mjs";
import type { Personalization, Branding, Preferences } from "@deck/contract";
import { PortError } from "../http-errors";
import type { AppearanceApi } from "../appearance";

export interface FakeAppearanceApi extends AppearanceApi {
  /** Makes the next call to `op` (a method name of the port) reject with `error`. */
  failNext(op: keyof AppearanceApi, error: Error): void;
}

/**
 * In memory, with the server's rules (the same shared validation): a member's colors and brand are
 * refused as a `403`, an invalid document as a `400`. `layout` starts the person with that Estilo saved.
 */
export function fakeAppearanceApi({ layout, isAdmin = true }: { layout?: string; isAdmin?: boolean } = {}): FakeAppearanceApi {
  let personal: Personalization | null = layout ? personalizationOf({ version: 1, preferences: { ...defaultPreferences, layout: layout as Preferences["layout"] }, profiles: [] }) : null;
  let branding: Branding = { ...defaultBranding };
  const failures = new Map<keyof AppearanceApi, Error>();
  const check = (op: keyof AppearanceApi) => {
    const error = failures.get(op);
    if (error) {
      failures.delete(op);
      throw error;
    }
  };
  const refused = (e: unknown): never => {
    throw new PortError("http", e instanceof AppearanceAccessError ? 403 : 400, e instanceof Error ? e.message : String(e));
  };
  return {
    async appearance() { check("appearance"); return structuredClone({ personal: effectivePersonalization(personal, branding, isAdmin), branding }); },
    async saveAppearance(value) {
      check("saveAppearance");
      try { personal = personalForActor(value, branding, isAdmin); } catch (e) { refused(e); }
      return structuredClone(personal!);
    },
    async saveBranding(value) {
      check("saveBranding");
      if (!isAdmin) throw new PortError("http", 403, "Solo el administrador puede cambiar la marca de instalación.");
      try { branding = brandingOf(value); } catch (e) { refused(e); }
      return structuredClone(branding);
    },
    failNext(op, error) { failures.set(op, error); },
  };
}
