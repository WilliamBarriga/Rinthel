/** The narrowest the Session's tools panel gets, in CSS pixels. */
export const MIN_TOOLS_WIDTH = 320;

/** Where the panel's width is kept across reloads. */
export const TOOLS_WIDTH_KEY = "deck.session-tools.width";

/** A width the panel may take: never under the minimum, never over `max` (what the window leaves). */
export function clampWidth(width: number, max: number): number {
  return Math.round(Math.max(MIN_TOOLS_WIDTH, Math.min(width, Math.max(MIN_TOOLS_WIDTH, max))));
}
