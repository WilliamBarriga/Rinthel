import { describe, expect, it } from "vitest";
import type { UserCreate, UserPublic, UsersList } from "@deck/contract";
import { PortError } from "./http-errors";
import { UsersAdminConflict, UsersAdminSessionsNotRetired, type UsersAdminApi } from "./users-admin";
import { fetchUsersAdminApi } from "./adapters/fetch-users-admin";
import { fakeUsersAdminApi, userFixture } from "./fakes/users-admin";

const USERS: UserPublic[] = [
  userFixture({ id: 1, username: "ana", role: "admin" }),
  userFixture({ id: 2, username: "beto", role: "miembro" }),
  userFixture({ id: 3, username: "cris", role: "admin", disabled: true }),
];

interface World {
  /** The id of the user asking. */
  me: number;
  /** Their role: a member is a 403 on everything. */
  role: "admin" | "miembro";
}

const conflict = (code: string, message: string) => Response.json({ detail: { code, message } }, { status: 409 });
const forbidden = () => Response.json({ detail: "admin required" }, { status: 403 });

/** A tiny stand-in for the daemon's `/identity/users`, with its own rules (not the fake's code). */
function identityServer(users: UserPublic[], { me, role }: World) {
  const rows = users.map((u) => ({ ...u }));
  let nextUser = 100;
  const enabledAdmins = () => rows.filter((u) => u.role === "admin" && !u.disabled);
  const guard = (target: UserPublic, loses: boolean): Response | null => {
    if (!loses || target.role !== "admin" || target.disabled) return null;
    if (target.id === me) return conflict("self_lockout", "un admin no puede desactivarse, borrarse ni quitarse el rol a sí mismo");
    if (enabledAdmins().length === 1) return conflict("last_admin", "la Instance no puede quedarse sin un admin activo");
    return null;
  };
  return async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(String(input), "http://deck");
    const method = init?.method ?? "GET";
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
    if (role !== "admin") return forbidden();
    if (url.pathname === "/api/identity/users") {
      if (method === "GET") return Response.json({ users: rows } satisfies UsersList);
      if (method === "POST") {
        if (rows.some((u) => u.username === body.username)) return conflict("username_taken", "username already exists");
        const row = userFixture({ id: nextUser++, username: String(body.username), role: body.role as "admin" | "miembro", notes: String(body.notes ?? "") });
        rows.push(row);
        return Response.json(row);
      }
    }
    const u = /^\/api\/identity\/users\/(\d+)$/.exec(url.pathname);
    if (u) {
      const target = rows.find((r) => r.id === Number(u[1]));
      if (method === "PATCH") {
        if (!target) return Response.json({ detail: "not found" }, { status: 404 });
        const loses = body.disabled === true || (body.role != null && body.role !== "admin");
        const blocked = guard(target, loses);
        if (blocked) return blocked;
        Object.assign(target, Object.fromEntries(Object.entries(body).filter(([k, v]) => k !== "password" && v !== null)));
        return Response.json(target);
      }
      if (method === "DELETE") {
        if (!target) return Response.json({ ok: true });
        const blocked = guard(target, true);
        if (blocked) return blocked;
        rows.splice(rows.indexOf(target), 1);
        return Response.json({ ok: true });
      }
    }
    return Response.json({ detail: "not found" }, { status: 404 });
  };
}

type Make = (users: UserPublic[], world?: Partial<World>) => UsersAdminApi;

/** Same suite for every adapter of the port; it only uses the interface. */
function usersAdminApiContract(name: string, make: Make) {
  const NEW: UserCreate = { username: "dora", password: "secreto-123", role: "miembro", notes: "nueva" };
  describe(`UsersAdminApi (${name})`, () => {
    it("listUsers devuelve los usuarios con su rol y estado, sin contraseña", async () => {
      const list = await make(USERS).listUsers();
      expect(list.map((u) => u.username)).toEqual(["ana", "beto", "cris"]);
      expect(list[1]).toMatchObject({ role: "miembro", disabled: false });
      expect(list[2]).toMatchObject({ disabled: true });
      expect(JSON.stringify(list)).not.toMatch(/password/);
    });

    it("createUser da de alta al usuario y no devuelve la contraseña", async () => {
      const api = make(USERS);
      const created = await api.createUser(NEW);
      expect(created).toMatchObject({ username: "dora", role: "miembro", notes: "nueva", disabled: false });
      expect(JSON.stringify(created)).not.toContain("secreto-123");
      expect((await api.listUsers()).map((u) => u.username)).toContain("dora");
    });

    it("createUser con un nombre repetido es un conflicto username_taken (409)", async () => {
      const error = await make(USERS).createUser({ ...NEW, username: "ana" }).catch((e: unknown) => e);
      expect(error).toBeInstanceOf(UsersAdminConflict);
      expect(error).toBeInstanceOf(PortError);
      expect(error).toMatchObject({ code: "username_taken", status: 409, kind: "http" });
    });

    it("updateUser cambia solo lo que se manda", async () => {
      const api = make(USERS);
      expect(await api.updateUser(2, { notes: "hola" })).toMatchObject({ id: 2, notes: "hola", role: "miembro" });
      expect(await api.updateUser(2, { disabled: true })).toMatchObject({ disabled: true, notes: "hola" });
      expect((await api.listUsers()).find((u) => u.id === 2)).toMatchObject({ disabled: true, notes: "hola" });
    });

    it("updateUser de un usuario que no existe es un 404", async () => {
      await expect(make(USERS).updateUser(999, { notes: "x" })).rejects.toMatchObject({ status: 404 });
    });

    it("un admin que se desactiva, se baja a miembro o se borra a sí mismo es un conflicto self_lockout (409) y no cambia nada", async () => {
      const api = make(USERS, { me: 1 });
      for (const run of [() => api.updateUser(1, { disabled: true }), () => api.updateUser(1, { role: "miembro" }), () => api.deleteUser(1)]) {
        const error = await run().catch((e: unknown) => e);
        expect(error).toBeInstanceOf(UsersAdminConflict);
        expect(error).toMatchObject({ code: "self_lockout", status: 409 });
      }
      expect((await api.listUsers()).find((u) => u.id === 1)).toMatchObject({ role: "admin", disabled: false });
    });

    it("dejar a la Instance sin un admin activo es un conflicto last_admin (409)", async () => {
      const api = make(USERS, { me: 99 });
      for (const run of [() => api.updateUser(1, { disabled: true }), () => api.updateUser(1, { role: "miembro" }), () => api.deleteUser(1)]) {
        await expect(run()).rejects.toMatchObject({ code: "last_admin", status: 409 });
      }
    });

    it("deleteUser borra al usuario; borrar uno que no existe no falla", async () => {
      const api = make(USERS);
      await api.deleteUser(2);
      expect((await api.listUsers()).map((u) => u.id)).toEqual([1, 3]);
      await api.deleteUser(2);
    });

    it("un miembro recibe 403 en todo", async () => {
      await expect(make(USERS, { role: "miembro" }).listUsers()).rejects.toMatchObject({ status: 403 });
    });
  });
}

usersAdminApiContract("fake", (users, world) => fakeUsersAdminApi({ users, ...world }));
// The fetch adapter gets its transport as a parameter: no global patching (ADR 0005).
usersAdminApiContract("fetch", (users, world) => fetchUsersAdminApi(identityServer(users, { me: 1, role: "admin", ...world })));

describe("fetchUsersAdminApi", () => {
  it("el 502 sessions_not_retired del daemon es un UsersAdminSessionsNotRetired con su mensaje", async () => {
    const api = fetchUsersAdminApi(async () => Response.json({ detail: { code: "sessions_not_retired", message: "deck answered 500" } }, { status: 502 }));
    const error = await api.deleteUser(2).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(UsersAdminSessionsNotRetired);
    expect(error).toMatchObject({ status: 502, message: "deck answered 500" });
  });

  it("un 502 sin código es el daemon caído: 'unavailable'", async () => {
    const api = fetchUsersAdminApi(async () => Response.json({ error: "daemon caído" }, { status: 502 }));
    await expect(api.listUsers()).rejects.toMatchObject({ kind: "unavailable" });
  });
});
