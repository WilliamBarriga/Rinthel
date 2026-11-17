import type { AuthStatus } from "../../ports/auth";

export type AuthSessionState =
  | { status: "checking" }
  | { status: "anonymous"; loginError?: string }
  | { status: "authed"; isAdmin: boolean; username?: string }
  | { status: "unavailable" }
  | { status: "failed"; message: string };

type Failure = { kind: string; message: string };
export type AuthSessionEvent =
  | { type: "checking" }
  | { type: "checked"; result: AuthStatus }
  | { type: "loggedIn"; result: AuthStatus | null }
  | { type: "loggedOut" }
  | { type: "loginFailed"; error: Failure }
  | { type: "operationFailed"; error: Failure }
  | { type: "portFailed"; error: Failure };

/** Admin only when the server says so: a status that could not be read grants nothing. */
const authenticated = (result: AuthStatus | null): AuthSessionState => ({
  status: "authed",
  isAdmin: result?.role === "admin",
  username: result?.username,
});

/** Pure authentication transitions, independent of React, cookies and error classes. */
export function authSessionReducer(state: AuthSessionState, event: AuthSessionEvent): AuthSessionState {
  switch (event.type) {
    case "checking": return { status: "checking" };
    case "checked": return event.result.authed ? authenticated(event.result) : { status: "anonymous" };
    case "loggedIn": return authenticated(event.result);
    case "loggedOut": return { status: "anonymous" };
    case "loginFailed": return event.error.kind === "unavailable" ? { status: "unavailable" }
      : { status: "anonymous", loginError: event.error.message };
    case "operationFailed":
    case "portFailed":
      if (event.error.kind === "unauthorized") return { status: "anonymous" };
      if (event.error.kind === "unavailable") return { status: "unavailable" };
      return event.type === "portFailed" ? state : { status: "failed", message: event.error.message };
  }
}
