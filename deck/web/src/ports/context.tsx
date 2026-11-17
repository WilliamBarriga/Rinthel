import { createContext, useContext, type ReactNode } from "react";
import type { AuthApi } from "./auth";
import type { UsersAdminApi } from "./users-admin";
import type { SessionsApi } from "./sessions";
import type { ModelsApi } from "./models";
import type { CanvasesApi } from "./canvases";
import type { AppearanceApi } from "./appearance";
import type { InstanceSoulApi } from "./instance-soul";
import type { BrowserApi } from "./browser";

/** Every port the front injects. Each port adds its own entry here. */
export interface Ports {
  authApi: AuthApi;
  usersAdminApi: UsersAdminApi;
  sessionsApi: SessionsApi;
  modelsApi: ModelsApi;
  canvasesApi: CanvasesApi;
  appearanceApi: AppearanceApi;
  instanceSoulApi: InstanceSoulApi;
  browserApi: BrowserApi;
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
export const useSessionsApi = () => usePort("sessionsApi");
export const useModelsApi = () => usePort("modelsApi");
export const useCanvasesApi = () => usePort("canvasesApi");
export const useAppearanceApi = () => usePort("appearanceApi");
export const useInstanceSoulApi = () => usePort("instanceSoulApi");
export const useBrowserApi = () => usePort("browserApi");
