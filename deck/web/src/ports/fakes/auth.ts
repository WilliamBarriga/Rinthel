import type { AuthApi } from "../auth";
import { PortError } from "../http-errors";

export interface FakeAuthApi extends AuthApi {
  /** Makes the next call to `op` (a method name of the port) reject with `error`. */
  failNext(op: keyof AuthApi, error: Error): void;
}

export interface FakeAuthOptions {
  /** username -> password. */
  users?: Record<string, string>;
  authed?: boolean;
  /** Role reported by `status` while logged in. */
  role?: "admin" | "miembro";
  username?: string;
}

export function fakeAuthApi({ users = {}, authed = false, role, username }: FakeAuthOptions = {}): FakeAuthApi {
  const failures = new Map<keyof AuthApi, Error>();
  const check = (op: keyof AuthApi) => {
    const error = failures.get(op);
    if (error) {
      failures.delete(op);
      throw error;
    }
  };
  return {
    async status() {
      check("status");
      return { authRequired: true, authed, ...(role && authed ? { role } : {}), ...(username && authed ? { username } : {}) };
    },
    async login(usernameInput, password) {
      check("login");
      if (users[usernameInput] !== password) throw new PortError("unauthorized", 401, "invalid credentials");
      authed = true;
      username = usernameInput;
    },
    async logout() {
      check("logout");
      authed = false;
    },
    failNext(op, error) {
      failures.set(op, error);
    },
  };
}
