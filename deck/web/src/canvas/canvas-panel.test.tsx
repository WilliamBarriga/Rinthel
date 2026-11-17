import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { fakePorts, renderWithPorts } from "../ports/testing";
import { canvasFixture, fakeCanvasesApi } from "../ports/fakes/canvases";
import { fakeSessionsApi, sessionFixture } from "../ports/fakes/sessions";
import { PortError } from "../ports/http-errors";
import { ChatPage } from "../chat/ChatPage";
import { CanvasPanel } from "./CanvasPanel";
import { canvasFile } from "./use-session-canvases";

afterEach(cleanup);

const form = {
  root: "f",
  state: { form: { topic: "" } },
  elements: {
    f: { type: "Stack", props: {}, children: ["topic", "send"] },
    topic: { type: "TextField", props: { label: "Tema", value: { $bindState: "/form/topic" } }, children: [] },
    send: {
      type: "Button", props: { label: "Pedir informe" }, children: [],
      on: { press: [{ action: "validateForm", params: {} }, { action: "askAgent", params: { message: { $template: "Quiero un informe de ${/form/topic}" } } }] },
    },
  },
};

function renderChat(canvasesApi = fakeCanvasesApi({ sessions: ["s1"] })) {
  renderWithPorts(
    <MemoryRouter initialEntries={["/sessions/s1"]}>
      <Routes><Route path="/sessions/:id" element={<ChatPage />} /></Routes>
    </MemoryRouter>,
    fakePorts({ sessionsApi: fakeSessionsApi({ sessions: [sessionFixture({ id: "s1", title: "Mi chat" })] }), canvasesApi }),
    { isAdmin: false },
  );
  return canvasesApi;
}
const panel = () => screen.findByRole("region", { name: "Espacio de Canvas de la Sesión" });

describe("the Canvas panel of a Session", () => {
  it("opens by itself when the Agent creates a document and shows what it writes", async () => {
    const api = renderChat();
    await screen.findByRole("heading", { name: "Mi chat" });
    expect(screen.queryByRole("region", { name: "Espacio de Canvas de la Sesión" })).toBeNull();
    act(() => api.write(canvasFixture({ id: "d", title: "Resumen", content: "# Hola\n\nTexto del Agente" }), "create"));
    const view = within(await panel());
    expect(view.getByRole("heading", { name: "Resumen" })).toBeTruthy();
    expect(await view.findByText("Texto del Agente")).toBeTruthy();
  });

  it("a ui canvas with a form: the person fills it, and its askAgent leaves the message for the Agent", async () => {
    const api = renderChat();
    await screen.findByRole("heading", { name: "Mi chat" });
    act(() => api.write(canvasFixture({ id: "u", kind: "ui", title: "Formulario", content: JSON.stringify(form) }), "create"));
    const view = within(await panel());
    fireEvent.change(await view.findByLabelText("Tema"), { target: { value: "ventas" } });
    fireEvent.click(view.getByRole("button", { name: "Pedir informe" }));
    expect((await view.findByRole("status")).textContent).toMatch(/Enviado al Agente/);
    expect(api.notes).toEqual([{ sessionId: "s1", text: "Quiero un informe de ventas" }]);
  });

  it("a refused action is told to the person, and the notice can be dismissed", async () => {
    const api = renderChat();
    await screen.findByRole("heading", { name: "Mi chat" });
    act(() => api.write(canvasFixture({ id: "u", kind: "ui", title: "Formulario", content: JSON.stringify(form) }), "create"));
    const view = within(await panel());
    api.failNext("act", new PortError("http", 403, "Forbidden"));
    fireEvent.click(await view.findByRole("button", { name: "Pedir informe" }));
    expect((await view.findByRole("alert")).textContent).toMatch(/Forbidden/);
    fireEvent.click(view.getByRole("button", { name: "Cerrar aviso del Canvas" }));
    await waitFor(() => expect(view.queryByRole("alert")).toBeNull());
  });

  it("picks among the Canvases of the Session, and a deleted one leaves the list", async () => {
    const api = renderChat(fakeCanvasesApi({ sessions: ["s1"], canvases: [canvasFixture({ id: "a", title: "Primero", content: "uno" }), canvasFixture({ id: "b", title: "Segundo", content: "dos" })] }));
    fireEvent.click(await screen.findByRole("button", { name: "Canvas de la Sesión" }));
    const view = within(await panel());
    fireEvent.change(view.getByRole("combobox", { name: "Seleccionar Canvas" }), { target: { value: "b" } });
    expect(await view.findByText("dos")).toBeTruthy();
    act(() => api.emit("s1", { type: "delete", id: "b" }));
    await waitFor(() => expect(view.queryByRole("option", { name: "Segundo" })).toBeNull());
  });

  it("downloads the selected Canvas: a .md for a document and a .json for an interface", () => {
    expect(canvasFile(canvasFixture({ id: "a", title: "Plan: 2026/Q1", content: "x" }))).toMatchObject({ filename: "Plan_ 2026_Q1.md", text: "x" });
    expect(canvasFile(canvasFixture({ id: "u", kind: "ui", title: "Panel", content: "{}" }))).toMatchObject({ filename: "Panel.json", mime: expect.stringContaining("json") });
  });

  it("the download button hands the selected Canvas to the browser", async () => {
    const saveFile = vi.fn();
    const canvasesApi = fakeCanvasesApi({ sessions: ["s1"], canvases: [canvasFixture({ id: "a", title: "Plan", content: "# Plan" })] });
    renderWithPorts(<CanvasPanel sessionId="s1" open setOpen={() => {}} saveFile={saveFile} />, fakePorts({ canvasesApi }));
    const view = within(await panel());
    fireEvent.click(await waitFor(() => { const b = view.getByRole("button", { name: "Descargar Canvas" }); expect((b as HTMLButtonElement).disabled).toBe(false); return b; }));
    expect(saveFile).toHaveBeenCalledWith({ filename: "Plan.md", text: "# Plan", mime: "text/markdown;charset=utf-8" });
  });

  it("closing the Chat stops following its Canvases", async () => {
    const api = renderChat();
    await screen.findByRole("heading", { name: "Mi chat" });
    await waitFor(() => expect(api.followers("s1")).toBe(1));
    cleanup();
    expect(api.followers("s1")).toBe(0);
  });
});
