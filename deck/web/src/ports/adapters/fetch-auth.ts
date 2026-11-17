import type { AuthApi, AuthStatus } from "../auth";
import { globalFetch, requestJson, type FetchLike } from "../http-errors";

/** The `fetch` adapter only knows HTTP: URL, status and JSON body. */
export function fetchAuthApi(fetchImpl: FetchLike = globalFetch): AuthApi {
  return {
    status: () => requestJson<AuthStatus>(fetchImpl, "/api/auth/status"),
    async login(username, password) {
      await requestJson(fetchImpl, "/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
    },
    async logout() {
      await requestJson(fetchImpl, "/api/auth/logout", { method: "POST" });
    },
  };
}
