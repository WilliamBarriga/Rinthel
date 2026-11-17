import { describe, expect, it } from "vitest";
import { fetchAuthApi } from "./adapters/fetch-auth";
import type { AuthApi } from "./auth";
import { fakeAuthApi } from "./fakes/auth";
import { PortError } from "./http-errors";

const USERS = { ana: "secreto" };

/** A tiny stand-in for the Node auth routes: a cookie flag, `401` on bad credentials. */
function authServer(users: Record<string, string>) {
  let authed = false;
  let currentUser: string | undefined;
  return async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url === "/api/auth/status" && method === "GET") return Response.json({ authRequired: true, authed, ...(authed ? { username: currentUser } : {}) });
    if (url === "/api/auth/login" && method === "POST") {
      const { username, password } = JSON.parse(String(init?.body));
      if (users[username] !== password) return Response.json({ error: "invalid credentials" }, { status: 401 });
      authed = true;
      currentUser = username;
      return Response.json({ ok: true });
    }
    if (url === "/api/auth/logout" && method === "POST") {
      authed = false;
      return Response.json({ ok: true });
    }
    return Response.json({ error: "not found" }, { status: 404 });
  };
}

/** Same suite for every adapter of the port; it only uses the interface. */
function authApiContract(name: string, make: (users: Record<string, string>) => AuthApi) {
  describe(`AuthApi (${name})`, () => {
    it("arranca sin sesión", async () => {
      expect(await make(USERS).status()).toEqual({ authRequired: true, authed: false });
    });

    it("login correcto abre la sesión", async () => {
      const api = make(USERS);
      await api.login("ana", "secreto");
      expect(await api.status()).toMatchObject({ authed: true, username: "ana" });
    });

    it("login con credenciales malas rechaza con 'unauthorized' y no abre sesión", async () => {
      const api = make(USERS);
      const err = await api.login("ana", "mala").catch((e) => e);
      expect(err).toBeInstanceOf(PortError);
      expect(err).toMatchObject({ kind: "unauthorized", status: 401 });
      expect((await api.status()).authed).toBe(false);
    });

    it("logout cierra la sesión", async () => {
      const api = make(USERS);
      await api.login("ana", "secreto");
      await api.logout();
      expect((await api.status()).authed).toBe(false);
    });
  });
}

authApiContract("fake", (users) => fakeAuthApi({ users }));
// The fetch adapter gets its transport as a parameter: no global patching (ADR 0005).
authApiContract("fetch", (users) => fetchAuthApi(authServer(users)));

describe("fetchAuthApi", () => {
  it("un 502 del proxy rechaza con 'unavailable'", async () => {
    const api = fetchAuthApi(async () => Response.json({ error: "daemon caído" }, { status: 502 }));
    await expect(api.status()).rejects.toMatchObject({ kind: "unavailable", message: "daemon caído" });
  });
  it("un 401 en status rechaza con 'unauthorized'", async () => {
    const api = fetchAuthApi(async () => Response.json({ error: "expired" }, { status: 401 }));
    await expect(api.status()).rejects.toMatchObject({ kind: "unauthorized" });
  });
});

describe("fakeAuthApi", () => {
  it("failNext hace fallar la siguiente llamada a la operación y solo esa", async () => {
    const api = fakeAuthApi({ users: USERS });
    api.failNext("status", new PortError("unavailable", 502, "daemon caído"));
    await expect(api.status()).rejects.toMatchObject({ kind: "unavailable" });
    expect((await api.status()).authed).toBe(false);
  });
});
