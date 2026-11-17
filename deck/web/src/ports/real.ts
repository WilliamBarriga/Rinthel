import type { Ports } from "./context";
import { fetchAuthApi } from "./adapters/fetch-auth";
import { fetchUsersAdminApi } from "./adapters/fetch-users-admin";
import { fetchSessionsApi } from "./adapters/fetch-sessions";
import { fetchModelsApi } from "./adapters/fetch-models";
import { fetchCanvasesApi } from "./adapters/fetch-canvases";
import { fetchAppearanceApi } from "./adapters/fetch-appearance";
import { fetchInstanceSoulApi } from "./adapters/fetch-instance-soul";

/** Composition root: the only place that picks the real adapters. */
export function realPorts(): Ports {
  return {
    authApi: fetchAuthApi(), usersAdminApi: fetchUsersAdminApi(), sessionsApi: fetchSessionsApi(), modelsApi: fetchModelsApi(),
    canvasesApi: fetchCanvasesApi(), appearanceApi: fetchAppearanceApi(), instanceSoulApi: fetchInstanceSoulApi(),
  };
}
