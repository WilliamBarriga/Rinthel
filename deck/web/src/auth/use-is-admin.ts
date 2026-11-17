import { createContext, useContext } from "react";

/** The session's admin flag, provided once by `App` from `useAuthSession` (the model owns the rule). */
export const IsAdminContext = createContext<boolean | null>(null);

/** Whether the reader is an admin (or the Instance needs no login). Reads the session `App` already holds; no extra request. */
export function useIsAdmin(): boolean {
  const isAdmin = useContext(IsAdminContext);
  if (isAdmin === null) throw new Error("useIsAdmin needs the IsAdminContext provider (App provides it)");
  return isAdmin;
}
