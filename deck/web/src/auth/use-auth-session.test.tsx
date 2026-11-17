import { describe, expect, it } from "vitest";
import { act, waitFor } from "@testing-library/react";
import { PortError } from "../ports/http-errors";
import { fakeAuthApi } from "../ports/fakes/auth";
import { fakePorts, renderHookWithPorts } from "../ports/testing";
import { useAuthSession } from "./use-auth-session";

const USERS = { ana: "secreto" };
const setup = (opts: Parameters<typeof fakeAuthApi>[0] = { users: USERS }) => {
  const authApi = fakeAuthApi(opts);
  return { authApi, ...renderHookWithPorts(() => useAuthSession(), fakePorts({ authApi })) };
};

describe("useAuthSession", () => {
  it("empieza comprobando y pasa a anónimo si no hay sesión", async () => {
    const { result } = setup();
    expect(result.current.state).toEqual({ status: "checking" });
    await waitFor(() => expect(result.current.state).toEqual({ status: "anonymous" }));
  });

  it("entra directo si ya hay sesión", async () => {
    const { result } = setup({ users: USERS, authed: true });
    await waitFor(() => expect(result.current.state).toEqual({ status: "authed", isAdmin: false }));
  });

  it("isAdmin sale del rol del usuario", async () => {
    const admin = setup({ users: USERS, authed: true, role: "admin" });
    await waitFor(() => expect(admin.result.current.state).toEqual({ status: "authed", isAdmin: true }));
    const member = setup({ users: USERS, authed: true, role: "miembro" });
    await waitFor(() => expect(member.result.current.state).toEqual({ status: "authed", isAdmin: false }));
  });

  it("tras el login lee el rol: un admin entra con isAdmin", async () => {
    const { result } = setup({ users: USERS, role: "admin" });
    await waitFor(() => expect(result.current.state.status).toBe("anonymous"));
    await act(() => result.current.login("ana", "secreto"));
    expect(result.current.state).toEqual({ status: "authed", isAdmin: true, username: "ana" });
  });

  it("un 401 al comprobar lleva al login", async () => {
    const authApi = fakeAuthApi({ users: USERS });
    authApi.failNext("status", new PortError("unauthorized", 401, "expired"));
    const { result } = renderHookWithPorts(() => useAuthSession(), fakePorts({ authApi }));
    await waitFor(() => expect(result.current.state).toEqual({ status: "anonymous" }));
  });

  it("un 502 muestra el aviso de servicio caído y 'retry' vuelve a comprobar", async () => {
    const authApi = fakeAuthApi({ users: USERS });
    authApi.failNext("status", new PortError("unavailable", 502, "daemon caído"));
    const { result } = renderHookWithPorts(() => useAuthSession(), fakePorts({ authApi }));
    await waitFor(() => expect(result.current.state).toEqual({ status: "unavailable" }));
    await act(() => result.current.retry());
    expect(result.current.state).toEqual({ status: "anonymous" });
  });

  it("otro fallo expone su mensaje sin lanzar", async () => {
    const authApi = fakeAuthApi({ users: USERS });
    authApi.failNext("status", new PortError("http", 500, "HTTP 500"));
    const { result } = renderHookWithPorts(() => useAuthSession(), fakePorts({ authApi }));
    await waitFor(() => expect(result.current.state).toEqual({ status: "failed", message: "HTTP 500" }));
  });

  it("login correcto entra; uno malo se queda en el login con el error", async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current.state.status).toBe("anonymous"));
    await act(() => result.current.login("ana", "mala"));
    expect(result.current.state).toEqual({ status: "anonymous", loginError: "invalid credentials" });
    await act(() => result.current.login("ana", "secreto"));
    expect(result.current.state).toEqual({ status: "authed", isAdmin: false, username: "ana" });
  });

  it("un 502 en el login muestra el aviso de servicio caído", async () => {
    const { result, authApi } = setup();
    await waitFor(() => expect(result.current.state.status).toBe("anonymous"));
    authApi.failNext("login", new PortError("unavailable", 502, "daemon caído"));
    await act(() => result.current.login("ana", "secreto"));
    expect(result.current.state).toEqual({ status: "unavailable" });
  });

  it("logout cierra la sesión y vuelve al login", async () => {
    const { result, authApi } = setup({ users: USERS, authed: true });
    await waitFor(() => expect(result.current.state.status).toBe("authed"));
    await act(() => result.current.logout());
    expect(result.current.state).toEqual({ status: "anonymous" });
    expect((await authApi.status()).authed).toBe(false);
  });

  it("un 502 al cerrar sesión muestra el aviso y no finge que cerró", async () => {
    const { result, authApi } = setup({ users: USERS, authed: true });
    await waitFor(() => expect(result.current.state.status).toBe("authed"));
    authApi.failNext("logout", new PortError("unavailable", 502, "daemon caído"));
    await act(() => result.current.logout());
    expect(result.current.state).toEqual({ status: "unavailable" });
  });

  it("reportFailure: un 401 de cualquier otro controlador manda al login; un 502 al aviso", async () => {
    const { result } = setup({ users: USERS, authed: true });
    await waitFor(() => expect(result.current.state.status).toBe("authed"));
    act(() => result.current.reportFailure(new PortError("http", 409, "x")));
    expect(result.current.state).toEqual({ status: "authed", isAdmin: false });
    act(() => result.current.reportFailure(new PortError("unavailable", 502, "x")));
    expect(result.current.state).toEqual({ status: "unavailable" });
    act(() => result.current.reportFailure(new PortError("unauthorized", 401, "x")));
    expect(result.current.state).toEqual({ status: "anonymous" });
  });
});
