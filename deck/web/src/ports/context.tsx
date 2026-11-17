import { createContext, useContext, type ReactNode } from "react";
import type { AuthApi } from "./auth";
import type { UsersAdminApi } from "./users-admin";

/** Every port the front injects. Each port adds its own entry here. */
export interface Ports {
  authApi: AuthApi;
  usersAdminApi: UsersAdminApi;
}

const PortsContext = createContext<Ports | null>(null);

export function PortsProvider({ ports, children }: { ports: Ports; children: ReactNode }) {
  return <PortsContext.Provider value={ports}>{children}</PortsContext.Provider>;
}

function usePort<K extends keyof Ports>(name: K): Ports[K] {
  const ports = useContext(PortsContext);
  if (!ports) throw new Error(`${name}: no PortsProvider above this component`);
  return ports[name];
}

export const useAuthApi = () => usePort("authApi");
export const useUsersAdminApi = () => usePort("usersAdminApi");
