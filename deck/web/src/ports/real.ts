import type { Ports } from "./context";
import { fetchAuthApi } from "./adapters/fetch-auth";
import { fetchUsersAdminApi } from "./adapters/fetch-users-admin";

/** Composition root: the only place that picks the real adapters. */
export function realPorts(): Ports {
  return { authApi: fetchAuthApi(), usersAdminApi: fetchUsersAdminApi() };
}
