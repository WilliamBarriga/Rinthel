import type { UserPublic, UsersList } from "@deck/contract";
import { globalFetch, PortError, requestJson, type FetchLike } from "../http-errors";
import { UsersAdminConflict, UsersAdminSessionsNotRetired, type UsersAdminApi, type UsersAdminConflictCode } from "../users-admin";

const CONFLICT_CODES: readonly UsersAdminConflictCode[] = ["self_lockout", "last_admin", "username_taken"];

/** The daemon nests a typed `409` conflict, or the delete's `502 sessions_not_retired`, as `{detail: {code, message}}`; either one without a known `code` stays a plain `PortError`. */
function typedErrorOf(error: PortError): PortError {
  if (error.status !== 409 && error.status !== 502) return error;
  const detail = (error.body as { detail?: unknown } | undefined)?.detail;
  if (detail && typeof detail === "object") {
    const { code, message } = detail as { code?: unknown; message?: unknown };
    if (error.status === 502) {
      return code === "sessions_not_retired" ? new UsersAdminSessionsNotRetired(typeof message === "string" && message ? message : error.message, error.body) : error;
    }
    const known = CONFLICT_CODES.find((c) => c === code);
    if (known) return new UsersAdminConflict(known, typeof message === "string" && message ? message : error.message, error.body);
  }
  return error;
}

async function withConflictCode<T>(call: Promise<T>): Promise<T> {
  try {
    return await call;
  } catch (e) {
    throw e instanceof PortError ? typedErrorOf(e) : e;
  }
}

/** The `fetch` adapter only knows HTTP: the path, the status and the JSON body. */
export function fetchUsersAdminApi(fetchImpl: FetchLike = globalFetch): UsersAdminApi {
  const user = (id: number) => `/api/identity/users/${id}`;
  const json = (body: unknown) => JSON.stringify(body);
  return {
    async listUsers() {
      return (await requestJson<UsersList>(fetchImpl, "/api/identity/users")).users;
    },
    createUser: (u) => withConflictCode(requestJson<UserPublic>(fetchImpl, "/api/identity/users", { method: "POST", body: json(u) })),
    updateUser: (id, patch) => withConflictCode(requestJson<UserPublic>(fetchImpl, user(id), { method: "PATCH", body: json(patch) })),
    async deleteUser(id) {
      await withConflictCode(requestJson(fetchImpl, user(id), { method: "DELETE" }));
    },
  };
}
