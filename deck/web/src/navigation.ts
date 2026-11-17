import type { IconType } from "react-icons";
import { LuGlobe, LuMessagesSquare, LuPalette, LuSettings, LuSparkles, LuUsers } from "react-icons/lu";
import { matchPath } from "react-router-dom";

export type Role = "usuario" | "admin";
export interface NavigationEntry {
  id: string;
  path: string;
  label: string;
  icon: IconType;
  group: "principal" | "administración";
  audience: "todos" | "admin";
  /** A destination reached from another screen (a Session's chat), not listed in the Sidebar. */
  hidden?: boolean;
}

/**
 * The destinations of the Sidebar, and who may visit each: the one registry `App` builds its routes
 * and `RouteGuard` from. A later slice adds its row here and its screen in `App`.
 */
export const NAVIGATION: readonly NavigationEntry[] = [
  { id: "sessions", path: "/", label: "Sesiones", icon: LuMessagesSquare, group: "principal", audience: "todos" },
  { id: "chat", path: "/sessions/:id", label: "Chat", icon: LuMessagesSquare, group: "principal", audience: "todos", hidden: true },
  { id: "soul", path: "/soul", label: "SOUL de la Instance", icon: LuSparkles, group: "principal", audience: "todos" },
  { id: "appearance", path: "/appearance", label: "Apariencia", icon: LuPalette, group: "principal", audience: "todos" },
  { id: "browser", path: "/browser", label: "Instance browser", icon: LuGlobe, group: "administración", audience: "admin" },
  { id: "users", path: "/users", label: "Usuarios", icon: LuUsers, group: "administración", audience: "admin" },
  { id: "settings", path: "/settings", label: "Ajustes", icon: LuSettings, group: "administración", audience: "admin" },
];

export function navigationFor(role: Role, entries = NAVIGATION) {
  return (["principal", "administración"] as const)
    .map(group => ({ group, entries: entries.filter(row => row.group === group && !row.hidden && visibleTo(role, row)) }))
    .filter(group => group.entries.length > 0);
}

/** Whether `role` may visit `path`: a registered destination by its audience; anything else is not a route. */
export function canVisit(role: Role, path: string, entries = NAVIGATION): boolean {
  const row = destinationFor(path, entries);
  return row ? visibleTo(role, row) : false;
}

export function destinationFor(path: string, entries = NAVIGATION) {
  return entries.find(row => matchPath({ path: row.path, end: row.path === "/" }, path));
}

function visibleTo(role: Role, row: NavigationEntry): boolean {
  return row.audience === "todos" || role === "admin";
}
