import type { SettingsRepo } from "./store/port.js";
import { brandingOf, personalizationOf, defaultBranding, effectivePersonalization, personalForActor, storedPersonalization, AppearanceAccessError } from "../../shared/dist/appearance.mjs";
import type { Branding, Personalization } from "@deck/contract";

/** Reuses the persistent key/value port; writes one complete document atomically. */
export function appearanceSettings(settings: SettingsRepo) {
  const personalKey = (userId: number | null) => `appearance:user:${userId ?? "local"}`;
  const brandingFrom = (all: Record<string, string>) => Object.hasOwn(all, "appearance:brand") ? brandingOf(JSON.parse(all["appearance:brand"])) : { ...defaultBranding };
  return {
    async read(userId: number | null, isAdmin = false) {
      const all = await settings.all();
      const key = personalKey(userId);
      const branding = brandingFrom(all);
      const personal = Object.hasOwn(all, key) ? personalizationOf(JSON.parse(all[key])) : null;
      return { personal: effectivePersonalization(personal, branding, isAdmin), branding };
    },
    async save(userId: number | null, value: unknown, isAdmin = false): Promise<Personalization> {
      const branding = brandingFrom(await settings.all());
      const config = personalForActor(value, branding, isAdmin);
      await settings.set(personalKey(userId), storedPersonalization(config, isAdmin)); return config;
    },
    async brand(value: unknown, isAdmin = false): Promise<Branding> {
      if (!isAdmin) throw new AppearanceAccessError("Solo el administrador puede cambiar la marca de instalación.");
      const current = brandingFrom(await settings.all());
      const sent = brandingOf(value);
      // A body without `palette` (older client, direct API) must not erase the shared palette.
      const config = sent.palette || !current.palette ? sent : { ...sent, palette: current.palette };
      await settings.set("appearance:brand", JSON.stringify(config)); return config;
    },
  };
}
