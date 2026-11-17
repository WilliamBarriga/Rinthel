import type { Appearance, Branding, Personalization } from "@deck/contract";

/**
 * Port: Apariencia y Personalización (`/api/appearance` of Node): the reader's own preferences and
 * profiles, and the Instance's brand and shared palette, which only the admin writes. Failures reject
 * with a `PortError`; a member who sends colors or a brand is a `403`, an invalid document a `400`,
 * and a stored document that cannot be read is a `409` (nothing is overwritten).
 */
export interface AppearanceApi {
  /** `personal` is null for factory values. */
  appearance(): Promise<Appearance>;
  saveAppearance(value: Personalization): Promise<Personalization>;
  /** Admin only. */
  saveBranding(value: Branding): Promise<Branding>;
}
