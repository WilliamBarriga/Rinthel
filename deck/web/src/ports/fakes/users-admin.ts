import type { UserPublic } from "@deck/contract";
import { PortError } from "../http-errors";
import { UsersAdminConflict, type UsersAdminApi } from "../users-admin";

export interface FakeUsersAdminApi extends UsersAdminApi {
  /** Replaces what the daemon holds, as if users changed elsewhere. */
  set(state: { users: readonly UserPublic[] }): void;
  /** Makes the next call to `op` (a method name of the port) reject with `error`. */
  failNext(op: keyof UsersAdminApi, error: Error): void;
  /** How many times `listUsers` was asked. */
  readonly calls: number;
  /** Every `createUser` that got in, password included: the one place a test can see what was sent. The rows never hold it. */
  readonly created: { username: string; password: string }[];
  /** Every user id `deleteUser` deleted, in order. */
  readonly deleted: number[];
}

export interface FakeUsersAdminOptions {
  users?: readonly UserPublic[];
  /** The id of the admin asking: the one the guard protects from themselves. */
  me?: number;
  /** Their role; a member is a `403` on every call. */
  role?: "admin" | "miembro";
}

export function userFixture(over: Partial<UserPublic> = {}): UserPublic {
  return {
    id: 1,
    username: "ana",
    role: "miembro",
    notes: "",
    created_at: "2026-10-01T08:00:00Z",
    disabled: false,
    ...over,
  };
}

/** In memory, with the daemon's rules: the guard of «sin admins / a sí mismo» as `409`, `404` for unknown ids, `403` for a member. A password is never held. */
export function fakeUsersAdminApi({ users = [], me = 1, role = "admin" }: FakeUsersAdminOptions = {}): FakeUsersAdminApi {
  let rows: UserPublic[] = users.map((u) => ({ ...u }));
  const failures = new Map<keyof UsersAdminApi, Error>();
  const created: { username: string; password: string }[] = [];
  const deleted: number[] = [];
  let calls = 0;
  let nextId = 1000;
  const enter = (op: keyof UsersAdminApi) => {
    const error = failures.get(op);
    if (error) {
      failures.delete(op);
      throw error;
    }
    if (role !== "admin") throw new PortError("http", 403, "admin required");
  };
  const find = (id: number) => {
    const row = rows.find((u) => u.id === id);
    if (!row) throw new PortError("http", 404, "not found");
    return row;
  };
  const enabledAdmins = () => rows.filter((u) => u.role === "admin" && !u.disabled);
  /** The guard: only an active admin losing admin is refused; themselves first, then the last one. */
  const guard = (target: UserPublic, loses: boolean) => {
    if (!loses || target.role !== "admin" || target.disabled) return;
    if (target.id === me) throw new UsersAdminConflict("self_lockout", "un admin no puede desactivarse, borrarse ni quitarse el rol a sí mismo");
    if (enabledAdmins().length === 1) throw new UsersAdminConflict("last_admin", "la Instance no puede quedarse sin un admin activo");
  };
  return {
    async listUsers() {
      calls++;
      enter("listUsers");
      return rows.map((u) => ({ ...u }));
    },
    async createUser(user) {
      enter("createUser");
      if (rows.some((u) => u.username === user.username)) throw new UsersAdminConflict("username_taken", "username already exists");
      created.push({ username: user.username, password: user.password });
      const row = userFixture({ id: nextId++, username: user.username, role: user.role, notes: user.notes ?? "" });
      rows.push(row);
      return { ...row };
    },
    async updateUser(id, patch) {
      enter("updateUser");
      const row = find(id);
      guard(row, patch.disabled === true || (patch.role != null && patch.role !== "admin"));
      if (patch.role != null) row.role = patch.role;
      if (patch.notes != null) row.notes = patch.notes;
      if (patch.disabled != null) row.disabled = patch.disabled;
      return { ...row };
    },
    async deleteUser(id) {
      enter("deleteUser");
      const row = rows.find((u) => u.id === id);
      if (!row) return;
      guard(row, true);
      deleted.push(id);
      rows = rows.filter((u) => u !== row);
    },
    set(state) {
      rows = state.users.map((u) => ({ ...u }));
    },
    failNext(op, error) {
      failures.set(op, error);
    },
    get calls() {
      return calls;
    },
    created,
    deleted,
  };
}
