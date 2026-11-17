import { expect, it } from "vitest";
import { authSessionReducer, type AuthSessionState } from "./auth-session";

it("a wrong password remains a login error; an expired authenticated session goes back to the login", () => {
  const anonymous: AuthSessionState = { status: "anonymous" };
  expect(authSessionReducer(anonymous, { type: "loginFailed", error: { kind: "unauthorized", message: "invalid credentials" } }))
    .toEqual({ status: "anonymous", loginError: "invalid credentials" });
  const loggedIn = authSessionReducer(anonymous, { type: "loggedIn", result: { authRequired: true, authed: true, role: "admin" } });
  expect(authSessionReducer(loggedIn, { type: "portFailed", error: { kind: "unauthorized", message: "expired" } }))
    .toEqual({ status: "anonymous" });
});

it("an unrelated port failure does not end a session; role-read failure grants no privileges", () => {
  const state: AuthSessionState = { status: "authed", isAdmin: true };
  expect(authSessionReducer(state, { type: "portFailed", error: { kind: "http", message: "conflict" } })).toBe(state);
  expect(authSessionReducer(state, { type: "loggedIn", result: null })).toMatchObject({ status: "authed", isAdmin: false });
  expect(authSessionReducer(state, { type: "operationFailed", error: { kind: "unavailable", message: "down" } })).toEqual({ status: "unavailable" });
});
