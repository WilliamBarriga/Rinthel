import type { Role } from "@deck/contract";

/** Port: the portal login. Cookies are HttpOnly, so the front only learns the outcome. */
export interface AuthStatus {
  /** Always `true`: Deck has no open mode. */
  authRequired: boolean;
  authed: boolean;
  /** The role of whoever is logged in, as the Instance has it now. */
  role?: Role;
  /** Verified Panel identity. */
  username?: string;
}

/**
 * Failures reject with a `PortError` (see `http-errors.ts`): a wrong password
 * is `unauthorized`, a daemon that is down is `unavailable`. There is no
 * `refresh` call: Node refreshes the cookies inside any request that needs it.
 */
export interface AuthApi {
  status(): Promise<AuthStatus>;
  login(username: string, password: string): Promise<void>;
  logout(): Promise<void>;
}
