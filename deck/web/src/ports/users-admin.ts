import type { UserCreate, UserPublic, UserUpdate } from "@deck/contract";
import { PortError } from "./http-errors";

/** Why the daemon refused with a `409`: the guard of «sin admins / a sí mismo», or a name already in use. */
export type UsersAdminConflictCode = "self_lockout" | "last_admin" | "username_taken";

/**
 * A `409` the screen can explain. It is a `PortError` (`kind: "http"`, `status: 409`,
 * `body` as the daemon sent it), so a caller that does not care still handles it as one.
 */
export class UsersAdminConflict extends PortError {
  constructor(
    readonly code: UsersAdminConflictCode,
    message: string,
    body?: unknown,
  ) {
    super("http", 409, message, body);
    this.name = "UsersAdminConflict";
  }
}

/**
 * The daemon's typed `502 {detail: {code: "sessions_not_retired", message}}` on a delete:
 * Deck did not retire the user's Sesiones, so nothing was deleted and the admin can retry.
 * Unlike a bare `502` (the daemon is down, kind `unavailable`) it carries a message to show.
 */
export class UsersAdminSessionsNotRetired extends PortError {
  readonly code = "sessions_not_retired";
  constructor(message: string, body?: unknown) {
    super("http", 502, message, body);
    this.name = "UsersAdminSessionsNotRetired";
  }
}

/**
 * Port: the admin's Usuarios (`/api/identity/users`, pass-through to the daemon, admin only: a
 * member is a `403` on every call). Types come from `@deck/contract`. Failures reject with a
 * `PortError`.
 *
 * `listUsers`, `createUser` (`username_taken` if the name exists), `updateUser` (a patch: only what
 * is sent changes; `404` for an unknown id) and `deleteUser` (an unknown id is not an error;
 * `UsersAdminSessionsNotRetired` if Deck could not retire their Sesiones, and nothing is deleted).
 * An admin disabling, demoting or deleting themselves is a `UsersAdminConflict` `self_lockout`;
 * leaving the Instance without an active admin is `last_admin`.
 *
 * Passwords are only ever sent: no reply carries one.
 */
export interface UsersAdminApi {
  listUsers(): Promise<UserPublic[]>;
  createUser(user: UserCreate): Promise<UserPublic>;
  updateUser(id: number, patch: UserUpdate): Promise<UserPublic>;
  deleteUser(id: number): Promise<void>;
}
