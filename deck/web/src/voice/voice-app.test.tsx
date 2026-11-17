import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { fakePorts, renderWithPorts } from "../ports/testing";
import { fakeSessionsApi, sessionFixture } from "../ports/fakes/sessions";
import { fakeVoiceSpeech } from "../ports/fakes/voice-speech";
import { PortError } from "../ports/http-errors";
import { ChatPage } from "../chat/ChatPage";
import { VoicePage } from "./VoicePage";
import { VoiceStage, type VoiceStageProps } from "./VoiceStage";

afterEach(cleanup);

function renderChat(voiceSpeech: ReturnType<typeof fakeVoiceSpeech>) {
  const sessionsApi = fakeSessionsApi({ sessions: [sessionFixture({ id: "s1", title: "Mi chat" })] });
  renderWithPorts(
    <MemoryRouter initialEntries={["/sessions/s1"]}>
      <Routes><Route path="/sessions/:id" element={<ChatPage />} /></Routes>
    </MemoryRouter>,
    fakePorts({ sessionsApi, voiceSpeech }),
    { isAdmin: false },
  );
}

describe("voice in a Session", () => {
  it("shows the microphone when the reader turned voice on and the Instance has stt and tts", async () => {
    renderChat(fakeVoiceSpeech({ config: { enabled: true } }));
    expect(await screen.findByRole("button", { name: "Activar voz manos libres" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Perfil de latencia de voz" })).toBeTruthy();
  });

  it("does not show it with the reader's voice off, nor without an active tts, and says nothing", async () => {
    renderChat(fakeVoiceSpeech({ config: { enabled: false } }));
    expect(await screen.findByRole("heading", { name: "Mi chat" })).toBeTruthy();
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByRole("button", { name: "Activar voz manos libres" })).toBeNull();
    cleanup();
    renderChat(fakeVoiceSpeech({ config: { enabled: true }, tts: false }));
    expect(await screen.findByRole("heading", { name: "Mi chat" })).toBeTruthy();
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByRole("button", { name: "Activar voz manos libres" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("appears once the reader turns voice on from Voz, without reloading the Session", async () => {
    const voiceSpeech = fakeVoiceSpeech({ config: { enabled: false } });
    renderChat(voiceSpeech);
    expect(await screen.findByRole("heading", { name: "Mi chat" })).toBeTruthy();
    await voiceSpeech.saveConfig({ enabled: true });
    window.dispatchEvent(new Event("voice-settings-changed"));
    expect(await screen.findByRole("button", { name: "Activar voz manos libres" })).toBeTruthy();
  });
});

describe("the Voz screen", () => {
  it("saves the reader's own settings: shown in their Sessions, the language and the detection", async () => {
    const voiceSpeech = fakeVoiceSpeech({ config: { enabled: false } });
    renderWithPorts(<VoicePage />, fakePorts({ voiceSpeech }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "Mostrar la voz en mis Sesiones" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Idioma de entrada" }), { target: { value: "es" } });
    fireEvent.change(screen.getByRole("slider", { name: /Silencio de fin de turno/ }), { target: { value: "1500" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar la voz" }));
    expect(await screen.findByRole("button", { name: "Guardado" })).toBeTruthy();
    expect(voiceSpeech.configSaved).toMatchObject([{ enabled: true, language: "es", vad: { redemptionMs: 1500 } }]);
  });

  it("says when the Instance has no active voice, and shows the server's refusal of a save", async () => {
    const voiceSpeech = fakeVoiceSpeech({ stt: false });
    renderWithPorts(<VoicePage />, fakePorts({ voiceSpeech }));
    expect((await screen.findByRole("note")).textContent).toContain("stt");
    voiceSpeech.failNext("saveConfig", new PortError("http", 400, "El umbral de fin de voz debe ser menor que el de inicio"));
    fireEvent.click(screen.getByRole("button", { name: "Guardar la voz" }));
    expect((await screen.findByRole("alert")).textContent).toContain("umbral de fin de voz");
    expect(voiceSpeech.configSaved).toEqual([]);
  });
});

describe("the voice stage", () => {
  const props = (over: Partial<VoiceStageProps> = {}): VoiceStageProps => ({
    title: "Mi chat", workPhase: null, phase: "Escuchando", starting: false, muted: false, speaking: false,
    levels: { current: { input: 0, output: 0 } }, transcript: "", error: "", events: [], sounds: true,
    onSounds: vi.fn(), onMute: vi.fn(), onEnd: vi.fn(), ...over,
  });

  it("says what voice is doing, previews what it hears, and its controls answer", () => {
    const p = props({ phase: "Te escucho", transcript: "dime la hora" });
    render(<VoiceStage {...p} />);
    expect(screen.getByRole("status").textContent).toBe("Te escucho");
    expect(screen.getByLabelText("Transcripción en vivo").textContent).toBe("dime la hora");
    fireEvent.click(screen.getByRole("button", { name: "Silenciar micrófono" }));
    fireEvent.click(screen.getByRole("button", { name: "Silenciar efectos de sonido" }));
    fireEvent.click(screen.getByRole("button", { name: "Terminar modo voz" }));
    expect([p.onMute, p.onSounds, p.onEnd].map((f) => (f as ReturnType<typeof vi.fn>).mock.calls.length)).toEqual([1, 1, 1]);
  });

  it("while muted the microphone reads so, and the orb is quiet", () => {
    render(<VoiceStage {...props({ muted: true })} />);
    expect(screen.getByRole("status").textContent).toBe("Micrófono silenciado");
    expect(screen.getByRole("button", { name: "Activar micrófono" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("the prompt's reading and a compaction show as progress in place of the status", async () => {
    const { rerender } = render(<VoiceStage {...props({ workPhase: { kind: "processing", prefill: { total: 40000, processed: 8000, cache: 8000, timeMs: 1 } } })} />);
    expect(screen.getByRole("progressbar", { name: "Procesamiento del prompt" }).getAttribute("aria-valuenow")).toBe("40");
    rerender(<VoiceStage {...props({ workPhase: { kind: "compacting", since: null } })} />);
    await waitFor(() => expect(screen.getByRole("progressbar", { name: "Compactación de la conversación" }).hasAttribute("aria-valuenow")).toBe(false));
  });
});
