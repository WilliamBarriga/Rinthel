import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { fakePorts, renderWithPorts } from "../ports/testing";
import { fakeBrowserApi, type FakeBrowserSeed } from "../ports/fakes/browser";
import { fakeSessionsApi, sessionFixture } from "../ports/fakes/sessions";
import { BrowserPage } from "./BrowserPage";
import { ChatPage } from "../chat/ChatPage";

afterEach(cleanup);

function renderBrowser(seed: FakeBrowserSeed = {}) {
  const browserApi = fakeBrowserApi(seed);
  renderWithPorts(<BrowserPage />, fakePorts({ browserApi }));
  return browserApi;
}

describe("the Instance browser screen", () => {
  it("a member reads only the refusal, and nothing of the browser", async () => {
    renderBrowser({ forbidden: true });
    expect((await screen.findByRole("alert")).textContent).toBe("Solo el administrador puede usar el browser de la Instance.");
    expect(screen.queryByRole("region", { name: "Estado del browser" })).toBeNull();
  });

  it("the admin installs only after giving it a password (suggested here), and it runs", async () => {
    const api = renderBrowser();
    const install = await screen.findByRole("button", { name: "Instalar" }) as HTMLButtonElement;
    expect(install.disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Sugerir contraseña" }));
    await waitFor(() => expect((screen.getByLabelText("Contraseña del browser") as HTMLInputElement).value).toBe("0123456789abcdef01234567"));
    fireEvent.click(screen.getByRole("button", { name: "Instalar" }));
    expect(await screen.findByRole("button", { name: "Detener" })).toBeTruthy();
    expect(api.log).toEqual(["config", "install"]);
    expect(screen.getByRole("region", { name: "Estado del browser" }).textContent).toMatch(/en marcha/);
  });

  it("the admin stops and starts it by hand", async () => {
    const api = renderBrowser({ container: "running", hasPassword: true });
    fireEvent.click(await screen.findByRole("button", { name: "Detener" }));
    fireEvent.click(await screen.findByRole("button", { name: "Arrancar" }));
    await screen.findByRole("button", { name: "Detener" });
    expect(api.log).toEqual(["stop", "start"]);
  });

  it("an external browser is only shown: no lifecycle buttons", async () => {
    renderBrowser({ mode: "external", container: "running", hasPassword: true });
    expect(await screen.findByText(/se administra fuera de Deck/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Instalar|Arrancar|Detener|Quitar/ })).toBeNull();
  });

  it("the allowlist is a draft until saved, and comes back one domain per line", async () => {
    const api = renderBrowser({ container: "running", hasPassword: true });
    const box = await screen.findByRole("textbox", { name: /uno por línea/ }) as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "a.example, *.b.example" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar dominios" }));
    await waitFor(() => expect(box.value).toBe("a.example\n*.b.example"));
    expect(api.log).toEqual(["allowlist"]);
  });

  it("over plain HTTP the view cannot run in a frame, so it links to the browser's own HTTPS port", async () => {
    renderBrowser({ container: "running", hasPassword: true, uiPort: "3011" });
    const link = await screen.findByRole("link", { name: /Abrir la vista del browser/ });
    expect(link.getAttribute("href")).toBe(`https://${window.location.hostname}:3011/`);
  });
});

function renderChat(isAdmin: boolean, browserApi = fakeBrowserApi({ container: "running", hasPassword: true })) {
  const sessionsApi = fakeSessionsApi({ sessions: [sessionFixture({ id: "s1", title: "Mi chat" })] });
  renderWithPorts(
    <MemoryRouter initialEntries={["/sessions/s1"]}><Routes><Route path="/sessions/:id" element={<ChatPage />} /></Routes></MemoryRouter>,
    fakePorts({ sessionsApi, browserApi }),
    { isAdmin },
  );
  return browserApi;
}

describe("a Session's browser", () => {
  it("a member's chat has no browser at all", async () => {
    renderChat(false);
    await screen.findByRole("heading", { name: "Mi chat" });
    expect(screen.queryByRole("button", { name: "Navegador de la Sesión" })).toBeNull();
  });

  it("the admin lets this Session's Agent use the browser, and the view stays mounted while hidden", async () => {
    const api = renderChat(true);
    fireEvent.click(await screen.findByRole("button", { name: "Navegador de la Sesión" }));
    const panel = screen.getByRole("complementary", { name: "Navegador de la Sesión" });
    const toggle = within(panel).getByRole("checkbox") as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    fireEvent.click(toggle);
    await waitFor(() => expect(toggle.checked).toBe(true));
    expect(api.log).toEqual(["session:s1:on"]);
    const frame = panel.querySelector("iframe")!;
    expect(frame.getAttribute("src")).toBe("/browser-ui/");
    fireEvent.click(within(panel).getByRole("button", { name: "Volver al chat" }));
    expect(screen.queryByRole("complementary", { name: "Navegador de la Sesión" })).toBeNull();
    expect(frame.isConnected).toBe(true);
  });

  it("with the browser stopped the panel says where it is started, and shows no frame", async () => {
    renderChat(true, fakeBrowserApi({ container: "stopped", hasPassword: true }));
    fireEvent.click(await screen.findByRole("button", { name: "Navegador de la Sesión" }));
    expect(screen.getByText(/no está en marcha/)).toBeTruthy();
    expect(document.querySelector("iframe")).toBeNull();
  });

  it("the panel's width moves by keyboard, between its limits", async () => {
    renderChat(true);
    fireEvent.click(await screen.findByRole("button", { name: "Navegador de la Sesión" }));
    const handle = screen.getByRole("separator", { name: "Ancho de herramientas" });
    const before = Number(handle.getAttribute("aria-valuenow"));
    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    await waitFor(() => expect(Number(handle.getAttribute("aria-valuenow"))).not.toBe(before));
    for (let i = 0; i < 40; i++) fireEvent.keyDown(handle, { key: "ArrowRight" });
    await waitFor(() => expect(Number(handle.getAttribute("aria-valuenow"))).toBe(320));
  });
});
