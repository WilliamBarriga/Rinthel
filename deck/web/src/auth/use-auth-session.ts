import { useCallback, useEffect, useReducer, useRef } from "react";
import { useAuthApi } from "../ports/context";
import { PortError, messageOf } from "../ports/http-errors";
import { authSessionReducer, type AuthSessionEvent } from "./model/auth-session";
export type { AuthSessionState } from "./model/auth-session";

const failure = (error: unknown) => ({ kind: error instanceof PortError ? error.kind : "unknown", message: messageOf(error) });

/** Coordinates authentication effects through its port; the model owns transitions. */
export function useAuthSession() {
  const api = useAuthApi();
  const [state, dispatch] = useReducer(authSessionReducer, { status: "checking" });
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => { live.current = false; };
  }, []);
  const send = useCallback((event: AuthSessionEvent) => {
    if (live.current) dispatch(event);
  }, []);

  const check = useCallback(async () => {
    try { send({ type: "checked", result: await api.status() }); }
    catch (error) { send({ type: "operationFailed", error: failure(error) }); }
  }, [api, send]);
  useEffect(() => { void check(); }, [check]);

  const login = useCallback(async (username: string, password: string) => {
    try {
      await api.login(username, password);
      // The login reply carries no role: fall back to no admin privileges if reading it fails.
      const result = await api.status().catch(() => null);
      send({ type: "loggedIn", result });
    } catch (error) { send({ type: "loginFailed", error: failure(error) }); }
  }, [api, send]);

  const logout = useCallback(async () => {
    try { await api.logout(); send({ type: "loggedOut" }); }
    catch (error) { send({ type: "operationFailed", error: failure(error) }); }
  }, [api, send]);
  const retry = useCallback(async () => { send({ type: "checking" }); await check(); }, [check, send]);
  const reportFailure = useCallback((error: unknown) => send({ type: "portFailed", error: failure(error) }), [send]);
  return { state, login, logout, retry, reportFailure };
}
