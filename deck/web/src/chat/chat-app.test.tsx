import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { fakePorts, renderWithPorts } from "../ports/testing";
import { fakeSessionsApi, sessionFixture } from "../ports/fakes/sessions";
import { fakeModelsApi, modelFixture, voiceFixture } from "../ports/fakes/models";
import { ChatPage } from "./ChatPage";
import { SessionsPage } from "../sessions/SessionsPage";
import { SettingsPage } from "../settings/SettingsPage";

afterEach(cleanup);

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}

function renderChat(options: { isAdmin?: boolean; models?: ReturnType<typeof fakeModelsApi> } = {}) {
  const sessionsApi = fakeSessionsApi({ sessions: [sessionFixture({ id: "s1", title: "Mi chat" })] });
  const modelsApi = options.models ?? fakeModelsApi({ role: options.isAdmin === false ? "miembro" : "admin" });
  renderWithPorts(
    <MemoryRouter initialEntries={["/sessions/s1"]}>
      <Routes><Route path="/sessions/:id" element={<ChatPage />} /></Routes>
    </MemoryRouter>,
    fakePorts({ sessionsApi, modelsApi }),
    { isAdmin: options.isAdmin ?? true },
  );
  return { sessionsApi, modelsApi };
}

describe("the chat of a Session", () => {
  it("a message goes to the Session and the Agent's answer reaches the transcript; the composer clears", async () => {
    const { sessionsApi } = renderChat({ isAdmin: false });
    expect(await screen.findByRole("heading", { name: "Mi chat" })).toBeTruthy();
    const box = screen.getByRole("textbox", { name: "Mensaje" }) as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "¿quién eres?" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByText("¿quién eres?")).toBeTruthy();
    expect((await screen.findByRole("article", { name: "Respuesta del Agente" })).textContent).toContain("hola");
    expect(sessionsApi.prompts).toEqual([{ id: "s1", message: "¿quién eres?" }]);
    expect(box.value).toBe("");
  });

  it("the composer shows the Local model and its window from the route; a member gets no picker", async () => {
    renderChat({ isAdmin: false });
    expect(await screen.findByText("qwen-a")).toBeTruthy();
    expect(await screen.findByText("66k de contexto")).toBeTruthy();
    expect(screen.queryByRole("combobox", { name: "Local model" })).toBeNull();
  });

  it("while llama-server reads the prompt the chat says how far it got, and Stop replaces Send", async () => {
    const { sessionsApi } = renderChat();
    await screen.findByRole("heading", { name: "Mi chat" });
    sessionsApi.emit("s1", "portal_status", { status: "running" });
    sessionsApi.emit("s1", "portal_prefill", { total: 200, cache: 100, processed: 50, timeMs: 5 }, true);
    expect((await screen.findByRole("status")).textContent).toMatch(/75%/);
    fireEvent.click(screen.getByRole("button", { name: "Detener" }));
    await waitFor(() => expect(sessionsApi.aborted).toEqual(["s1"]));
    expect(await screen.findByRole("button", { name: "Enviar" })).toBeTruthy();
  });

  it("the admin switches the Local model from the composer; a 409 with turns in course is shown there", async () => {
    const models = fakeModelsApi();
    renderChat({ models });
    const picker = await screen.findByRole("combobox", { name: "Local model" });
    fireEvent.change(picker, { target: { value: "qwen-b" } });
    models.refuse = "turns_in_flight";
    fireEvent.click(screen.getByRole("button", { name: "Cambiar modelo" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/turnos en curso/);
    expect(models.activated).toEqual([]);
    models.refuse = null;
    fireEvent.click(screen.getByRole("button", { name: "Cambiar modelo" }));
    await waitFor(() => expect(models.activated).toEqual(["qwen-b"]));
    expect(await screen.findByText("qwen-b")).toBeTruthy();
  });

  it("the Guard's refusal and an extension's dialog are in the transcript, and the dialog is answered", async () => {
    const { sessionsApi } = renderChat();
    await screen.findByRole("heading", { name: "Mi chat" });
    sessionsApi.emit("s1", "portal_guard", { tool: "bash", verdict: "deny", reason: "publish: pushing to a remote" });
    sessionsApi.emit("s1", "extension_ui_request", { id: "d1", method: "confirm", title: "¿Continuar?" }, true);
    expect((await screen.findByRole("note")).textContent).toMatch(/El Guard detuvo bash/);
    fireEvent.click(within(await screen.findByRole("dialog", { name: "¿Continuar?" })).getByRole("button", { name: "Sí" }));
    await waitFor(() => expect(sessionsApi.answered).toEqual([{ id: "s1", dialog: "d1", answer: { value: true } }]));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});


describe("Sesiones and Ajustes", () => {
  it("a new chat opens its Session; a task opens on a chosen workspace", async () => {
    const sessionsApi = fakeSessionsApi({ workspaces: ["proyecto"] });
    renderWithPorts(
      <MemoryRouter initialEntries={["/"]}>
        <Routes><Route path="/" element={<SessionsPage username="ana" />} /><Route path="/sessions/:id" element={<Where />} /></Routes>
      </MemoryRouter>,
      fakePorts({ sessionsApi }),
    );
    fireEvent.click(await screen.findByRole("button", { name: /Nuevo chat/ }));
    expect((await screen.findByTestId("where")).textContent).toBe("/sessions/chat-1");
  });

  it("the admin changes the Local model in Ajustes", async () => {
    const models = fakeModelsApi();
    renderWithPorts(<SettingsPage />, fakePorts({ modelsApi: models }));
    fireEvent.change(await screen.findByRole("combobox", { name: "Local model" }), { target: { value: "qwen-b" } });
    fireEvent.click(screen.getByRole("button", { name: "Cambiar modelo" }));
    await waitFor(() => expect(models.activated).toEqual(["qwen-b"]));
  });

  it("the admin turns the Instance's voice on and off in Ajustes, apart from the Local model", async () => {
    const models = fakeModelsApi({
      models: [modelFixture("qwen-a"), voiceFixture("whisper", "stt"), voiceFixture("pocket", "tts")],
      voice: { stt: null, tts: "pocket" },
    });
    renderWithPorts(<SettingsPage />, fakePorts({ modelsApi: models }));
    const llm = await screen.findByRole("combobox", { name: "Local model" });
    expect(within(llm).queryByRole("option", { name: /whisper|pocket/ })).toBeNull();

    const stt = screen.getByRole("group", { name: "Reconocimiento de voz (stt)" });
    expect(within(stt).getByText("Apagado")).toBeTruthy();
    expect(within(stt).getByRole("button", { name: "Apagar" })).toHaveProperty("disabled", true);
    fireEvent.click(within(stt).getByRole("button", { name: "Activar" }));
    await waitFor(() => expect(models.activated).toEqual(["whisper"]));
    await waitFor(() => expect(within(stt).getByText("Activo: whisper")).toBeTruthy());

    const tts = screen.getByRole("group", { name: "Síntesis de voz (tts)" });
    fireEvent.click(within(tts).getByRole("button", { name: "Apagar" }));
    await waitFor(() => expect(models.turnedOff).toEqual(["tts"]));
    await waitFor(() => expect(within(tts).getByText("Apagado")).toBeTruthy());
  });
});
