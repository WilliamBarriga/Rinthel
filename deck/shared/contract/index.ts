/**
 * The types the server and the front import as `@deck/contract`: Node's own routes and the
 * daemon's routes Deck uses (users, session-principal, Local models), the latter written by hand.
 *
 * Convention: one file per domain (`sessions.ts`), types only (no infrastructure nor runtime
 * values), re-exported here. Each port adds its own.
 */
export type * from "./sessions.js";
export type * from "./identity.js";
export type * from "./models.js";
export type * from "./events.js";
export type * from "./canvases.js";
export type * from "./instance-soul.js";
export type * from "./browser.js";
export type { Preferences, Personalization, Branding, Appearance } from "../appearance.mjs";
