import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import App from "../App";
import { fakeAuthApi } from "../ports/fakes/auth";
import { fakeUsersAdminApi, userFixture, type FakeUsersAdminApi } from "../ports/fakes/users-admin";
import { UsersAdminSessionsNotRetired } from "../ports/users-admin";
import { fakePorts, renderWithPorts } from "../ports/testing";

beforeAll(() => {
  window.matchMedia ??= ((query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {} })) as unknown as typeof window.matchMedia;
});
afterEach(cleanup);

const USERS = [
  userFixture({ id: 1, username: "root", role: "admin" }),
  userFixture({ id: 2, username: "ana", notes: "Jefa de ventas" }),
  userFixture({ id: 3, username: "beto", disabled: true }),
];

let api: FakeUsersAdminApi;

function Location() {
  return <output aria-label="Ruta actual">{useLocation().pathname}</output>;
}

function renderApp(path: string, { role = "admin" as "admin" | "miembro", username = "root", authed = true } = {}) {
  api = fakeUsersAdminApi({ users: USERS, me: 1, role });
  const authApi = fakeAuthApi({ users: { root: "root-password", ana: "ana-password" }, authed, role, username });
  return renderWithPorts(<MemoryRouter initialEntries={[path]}><App /><Location /></MemoryRouter>, fakePorts({ authApi, usersAdminApi: api }));
}
const route = () => screen.getByLabelText("Ruta actual").textContent;
const rows = () => screen.getAllByRole("row").slice(1);
const button = (name: string) => screen.getByRole("button", { name }) as HTMLButtonElement;

describe("login", () => {
  it("sin sesión pide usuario y contraseña; con la correcta entra al inicio", async () => {
    renderApp("/", { authed: false });
    fireEvent.change(await screen.findByLabelText("Usuario"), { target: { value: "ana" } });
    fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "mala" } });
    fireEvent.click(button("Iniciar sesión"));
    expect(await screen.findByRole("alert")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "ana-password" } });
    fireEvent.click(button("Iniciar sesión"));
    expect(await screen.findByRole("heading", { name: "Hola, ana" })).toBeTruthy();
  });

  it("cerrar sesión vuelve al login", async () => {
    renderApp("/");
    fireEvent.click(await screen.findByRole("button", { name: "Cerrar sesión" }));
    expect(await screen.findByRole("button", { name: "Iniciar sesión" })).toBeTruthy();
  });
});

describe("Usuarios: solo el admin", () => {
  it("un miembro no ve la entrada ni la pantalla: /users lo devuelve al inicio", async () => {
    renderApp("/users", { role: "miembro", username: "ana" });
    expect(await screen.findByRole("heading", { name: "Hola, ana" })).toBeTruthy();
    expect(route()).toBe("/");
    expect(screen.queryByRole("button", { name: "Usuarios" })).toBeNull();
    expect(api.calls).toBe(0);
  });

  it("el admin llega desde la barra y ve usuario, rol y estado; sin Grupos", async () => {
    renderApp("/");
    fireEvent.click(await screen.findByRole("button", { name: "Usuarios" }));
    expect(await screen.findByRole("heading", { name: "Usuarios" })).toBeTruthy();
    expect(route()).toBe("/users");
    await screen.findByText("ana");
    expect(screen.getAllByRole("columnheader").map(h => h.textContent)).toEqual(["Usuario", "Rol", "Estado"]);
    const beto = rows().find(r => within(r).queryByText("beto"))!;
    expect(within(beto).getByText("Desactivado")).toBeTruthy();
    expect(screen.queryByText(/Grupo/)).toBeNull();
  });
});

describe("Usuarios: crear y editar", () => {
  it("crea un usuario con su contraseña y lo abre en el panel", async () => {
    renderApp("/users/new");
    fireEvent.change(await screen.findByLabelText("Nombre de usuario"), { target: { value: "dora" } });
    fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "corta" } });
    fireEvent.click(button("Crear usuario"));
    expect(await screen.findByText(/al menos 8 caracteres/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "dora-password" } });
    fireEvent.click(button("Crear usuario"));
    expect(await screen.findByRole("heading", { name: "dora" })).toBeTruthy();
    expect(api.created).toEqual([{ username: "dora", password: "dora-password" }]);
  });

  it("un nombre repetido se dice en su campo y conserva lo escrito", async () => {
    renderApp("/users/new");
    fireEvent.change(await screen.findByLabelText("Nombre de usuario"), { target: { value: "ana" } });
    fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "ana-password-2" } });
    fireEvent.click(button("Crear usuario"));
    expect(await screen.findByText("Ese nombre de usuario ya existe.")).toBeTruthy();
    expect((screen.getByLabelText("Nombre de usuario") as HTMLInputElement).value).toBe("ana");
  });

  it("edita notas y rol; el admin no puede quitarse el rol a sí mismo", async () => {
    renderApp("/users/2");
    await screen.findByRole("heading", { name: "ana" });
    fireEvent.change(screen.getByLabelText("Notas"), { target: { value: "Gerente" } });
    fireEvent.click(button("Guardar"));
    expect(await screen.findByText("Cambios guardados")).toBeTruthy();
    expect((await api.listUsers()).find(u => u.id === 2)?.notes).toBe("Gerente");
    cleanup();
    renderApp("/users/1");
    await screen.findByRole("heading", { name: "root" });
    expect((screen.getByLabelText("Rol") as HTMLSelectElement).disabled).toBe(true);
  });

  it("desactivar y reactivar se aplican en el acto", async () => {
    renderApp("/users/2");
    await screen.findByRole("heading", { name: "ana" });
    fireEvent.click(button("Desactivar usuario"));
    expect(await screen.findByRole("button", { name: "Reactivar usuario" })).toBeTruthy();
    expect((await api.listUsers()).find(u => u.id === 2)?.disabled).toBe(true);
  });
});

describe("Usuarios: borrar", () => {
  it("pide escribir el nombre; al confirmar se borra y vuelve a la tabla", async () => {
    renderApp("/users/2");
    await screen.findByRole("heading", { name: "ana" });
    fireEvent.click(button("Borrar usuario"));
    const confirm = await screen.findByRole("region", { name: "Confirmar borrado" });
    expect(confirm.textContent).toMatch(/Sesiones/);
    expect(button("Borrar definitivamente").disabled).toBe(true);
    fireEvent.change(within(confirm).getByLabelText("Escribe ana para confirmar"), { target: { value: "ana" } });
    fireEvent.click(button("Borrar definitivamente"));
    await waitFor(() => expect(route()).toBe("/users"));
    expect(api.deleted).toEqual([2]);
    expect(screen.queryByText("ana")).toBeNull();
  });

  it("si Deck no retiró sus Sesiones, el usuario queda y se dice por qué", async () => {
    renderApp("/users/2");
    await screen.findByRole("heading", { name: "ana" });
    api.failNext("deleteUser", new UsersAdminSessionsNotRetired("deck answered 500"));
    fireEvent.click(button("Borrar usuario"));
    fireEvent.change(await screen.findByLabelText("Escribe ana para confirmar"), { target: { value: "ana" } });
    fireEvent.click(button("Borrar definitivamente"));
    expect((await screen.findByRole("alert")).textContent).toMatch(/Sesiones/);
    expect(route()).toBe("/users/2");
    expect(api.deleted).toEqual([]);
  });

  it("el admin no puede borrarse a sí mismo", async () => {
    renderApp("/users/1");
    await screen.findByRole("heading", { name: "root" });
    expect(button("Borrar usuario").disabled).toBe(true);
  });
});
