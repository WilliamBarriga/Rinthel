/**
 * The daemon's identity area as Deck reads it, written by hand: the daemon declares the same shapes in
 * `rinthel/rinthel_tui/api/identity/dtos.py`, and a change there is a change here. Deck relays
 * `/identity/users` to the front unchanged and reads the rest itself.
 */

export type Role = "admin" | "miembro";

/** `POST /identity/login` and `/identity/refresh`. */
export interface LoginSession {
  access_token: string;
  refresh_token: string;
  /** Seconds. */
  access_expires_in: number;
  user: { id: number; username: string; role: Role };
}

/** `GET /identity/me/session-principal`, as the service acting for the user. */
export interface SessionPrincipalDto {
  user_id: number;
  role: Role;
}

/** A user as an admin reads it. No reply ever carries a password. */
export interface UserPublic {
  id: number;
  username: string;
  role: Role;
  notes: string;
  created_at: string;
  disabled: boolean;
}

/** `GET /identity/users`. */
export interface UsersList {
  users: UserPublic[];
}

/** `POST /identity/users`. The password has at least 8 characters. */
export interface UserCreate {
  username: string;
  password: string;
  role: Role;
  notes?: string;
}

/** `PATCH /identity/users/:id`: only what is sent changes. */
export interface UserUpdate {
  role?: Role | null;
  notes?: string | null;
  disabled?: boolean | null;
  password?: string | null;
}

/** The daemon's coded refusals: `{ detail: { code, message } }`. */
export interface CodedDetail {
  code: string;
  message: string;
}
