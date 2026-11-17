import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import App from "./App";
import { NAVIGATION } from "./navigation";
import { fakeAuthApi } from "./ports/fakes/auth";
import { fakeAppearanceApi } from "./ports/fakes/appearance";
import { fakeInstanceSoulApi } from "./ports/fakes/instance-soul";
import { PortError } from "./ports/http-errors";
import { fakePorts, renderWithPorts } from "./ports/testing";

afterEach(cleanup);
beforeAll(() => {
  window.matchMedia ??= ((query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {} })) as unknown as typeof window.matchMedia;
});
function Location() { return <output aria-label="Current route">{useLocation().pathname}</output>; }

function mount(path: string, role: "admin" | "miembro", ports: Parameters<typeof fakePorts>[0] = {}) {
  const isAdmin = role === "admin";
  const instanceSoulApi = ports?.instanceSoulApi ?? fakeInstanceSoulApi({ soul: "# Rinthel\n", isAdmin });
  const appearanceApi = ports?.appearanceApi ?? fakeAppearanceApi({ isAdmin });
  renderWithPorts(<MemoryRouter initialEntries={[path]}><App /><Location /></MemoryRouter>,
    fakePorts({ authApi: fakeAuthApi({ authed: true, role }), instanceSoulApi, appearanceApi }));
  return { instanceSoulApi, appearanceApi };
}

describe("the Instance SOUL screen", () => {
  it("a member sees it and cannot edit it", async () => {
    mount("/soul", "miembro");
    const editor = await screen.findByRole("textbox", { name: "Contenido de la SOUL de la Instance" }) as HTMLTextAreaElement;
    await waitFor(() => expect(editor.value).toBe("# Rinthel\n"));
    expect(editor.readOnly).toBe(true);
    expect(screen.queryByRole("button", { name: "Guardar" })).toBeNull();
    expect(screen.getByText(/La edita el administrador/)).toBeTruthy();
  });

  it("the admin edits it and saves it; the member's view then reads the change", async () => {
    const { instanceSoulApi } = mount("/soul", "admin");
    const editor = await screen.findByRole("textbox", { name: "Contenido de la SOUL de la Instance" }) as HTMLTextAreaElement;
    await waitFor(() => expect(editor.value).toBe("# Rinthel\n"));
    expect(editor.readOnly).toBe(false);
    fireEvent.change(editor, { target: { value: "# Rinthel\nSobrio." } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText("Guardada")).toBeTruthy();
    expect((await instanceSoulApi.read()).content).toBe("# Rinthel\nSobrio.\n");
  });

  it("a refused save leaves the text as typed and says why", async () => {
    const instanceSoulApi = fakeInstanceSoulApi({ soul: "# Rinthel\n" });
    mount("/soul", "admin", { instanceSoulApi });
    const editor = await screen.findByRole("textbox", { name: "Contenido de la SOUL de la Instance" }) as HTMLTextAreaElement;
    await waitFor(() => expect(editor.value).toBe("# Rinthel\n"));
    instanceSoulApi.failNext("save", new PortError("http", 400, "La SOUL no puede pasar de 20000 caracteres"));
    fireEvent.change(editor, { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/20000/);
    expect(editor.value).toBe("x");
  });

  it("without a SOUL it says members load none", async () => {
    mount("/soul", "admin", { instanceSoulApi: fakeInstanceSoulApi({ soul: null }) });
    expect(await screen.findByText(/Todavía no está definida/)).toBeTruthy();
  });
});

describe("the Appearance screen", () => {
  it("is for everyone, and the brand tab and shared palette are the admin's", async () => {
    mount("/appearance", "miembro");
    const tabs = await screen.findByRole("tablist", { name: "Secciones de Personalización" });
    expect(within(tabs).getAllByRole("tab").map((t) => t.textContent)).toEqual(["Estilo", "Lectura", "Paneles", "Perfiles"]);
    cleanup();
    mount("/appearance", "admin");
    const adminTabs = await screen.findByRole("tablist", { name: "Secciones de Personalización" });
    expect(within(adminTabs).getAllByRole("tab").map((t) => t.textContent)).toEqual(["Estilo", "Marca", "Lectura", "Paneles", "Perfiles"]);
  });

  it("a member picks a style and applies it; it is saved for them", async () => {
    const { appearanceApi } = mount("/appearance", "miembro");
    await waitFor(() => expect((screen.getByRole("button", { name: "Aplicar preferencias" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("radio", { name: /Operación/ }));
    expect(document.documentElement.dataset.layout).toBe("operation");
    fireEvent.click(screen.getByRole("button", { name: "Aplicar preferencias" }));
    await waitFor(async () => expect((await appearanceApi.appearance()).personal?.preferences.layout).toBe("operation"));
  });

  it("the admin saves the installation brand and the Sidebar wears it", async () => {
    mount("/appearance", "admin");
    await waitFor(() => expect((screen.getByRole("button", { name: "Aplicar preferencias" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("tab", { name: "Marca" }));
    fireEvent.change(screen.getByLabelText("Nombre de instalación"), { target: { value: "Mi Instance" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar marca de instalación" }));
    expect(await screen.findByText("Marca de instalación guardada.")).toBeTruthy();
    expect(within(screen.getByRole("navigation", { name: "Navegación" })).getByText("Mi Instance")).toBeTruthy();
  });
});

describe("the Sidebar", () => {
  it("lists the surfaces that stay, for everyone, and none of the ones that left", () => {
    expect(NAVIGATION.map((e) => e.id)).toEqual(["sessions", "chat", "soul", "appearance", "voice", "browser", "users", "settings"]);
    for (const left of ["sources", "audit", "legacy", "guard-log", "model-audit"]) expect(NAVIGATION.some((e) => e.id === left || e.path.includes(left))).toBe(false);
  });

  it("a member sees Sesiones, SOUL and Apariencia, and no administration", async () => {
    mount("/", "miembro");
    const nav = await screen.findByRole("navigation", { name: "Navegación" });
    expect(within(nav).getAllByRole("button").map((b) => b.textContent).filter((t) => /Sesiones|SOUL|Apariencia|Usuarios|Ajustes/.test(t ?? "")))
      .toEqual(["Sesiones", "SOUL de la Instance", "Apariencia"]);
  });

  it("the routes of what left go back home", async () => {
    mount("/audit", "admin");
    await waitFor(() => expect(screen.getByLabelText("Current route").textContent).toBe("/"));
  });
});
