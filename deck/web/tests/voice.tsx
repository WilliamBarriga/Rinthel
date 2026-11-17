// Development-only harness for the voice spec: the real chat of a Session (`ChatPage`) and its voice
// mode, with the real voice adapter (its `/api/voice*` requests are answered by the spec) and the
// Session's stream in memory, driven by the buttons below. The microphone is a synthetic stream the
// spec feeds a WAV into; the physical one is never used.
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ChatPage } from "../src/chat/ChatPage";
import { PortsProvider, type Ports } from "../src/ports/context";
import { IsAdminContext } from "../src/auth/use-is-admin";
import { AppearanceProvider } from "../src/appearance/Appearance";
import { ThemeSwitcher } from "../src/components/ThemeSwitcher";
import { fakeSessionsApi, sessionFixture } from "../src/ports/fakes/sessions";
import { fakeAuthApi } from "../src/ports/fakes/auth";
import { fakeUsersAdminApi } from "../src/ports/fakes/users-admin";
import { fakeModelsApi } from "../src/ports/fakes/models";
import { fakeCanvasesApi } from "../src/ports/fakes/canvases";
import { fakeAppearanceApi } from "../src/ports/fakes/appearance";
import { fakeInstanceSoulApi } from "../src/ports/fakes/instance-soul";
import { fetchVoiceSpeech } from "../src/ports/adapters/fetch-voice-speech";
import "../src/index.css";
import "../src/base.css";
import "../src/appearance/appearance.css";

const ID = "test";
const microphone = new AudioContext();
let micRequests = 0;
let destination = microphone.createMediaStreamDestination();
Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
  value: async () => {
    micRequests++;
    if (destination.stream.getTracks().every((t) => t.readyState === "ended")) destination = microphone.createMediaStreamDestination();
    return destination.stream;
  },
});

const sessionsApi = fakeSessionsApi({ sessions: [sessionFixture({ id: ID, title: "Un espacio para pensar" })], answer: "Here is the spoken response." });
sessionsApi.emit(ID, "portal_prompt", { message: "Help me plan the next step.", turn_id: "t0" });
sessionsApi.emit(ID, "message_end", { streamId: "m0", message: { role: "assistant", content: [{ type: "text", text: "We can work through it together." }] } });

const counters = { sent: 0, voice: false, aborted: 0, changed: () => {} };
const ports: Ports = {
  authApi: fakeAuthApi(), usersAdminApi: fakeUsersAdminApi(), modelsApi: fakeModelsApi(), canvasesApi: fakeCanvasesApi({ sessions: [ID] }),
  appearanceApi: fakeAppearanceApi(), instanceSoulApi: fakeInstanceSoulApi(), voiceSpeech: fetchVoiceSpeech(),
  sessionsApi: {
    ...sessionsApi,
    // The Agent answers at once and keeps working, so speaking again interrupts it (barge-in).
    async prompt(id, message, options) {
      const turn = `t${++counters.sent}`;
      counters.voice = options?.voice === true;
      counters.changed();
      queueMicrotask(() => {
        emit("portal_prompt", { message, turn_id: turn });
        emit("portal_status", { status: "running" });
        emit("message_end", { streamId: `r-${turn}`, message: { role: "assistant", content: [{ type: "text", text: "Here is the spoken response." }] } });
      });
      return { ok: true, status: "running", queued: false, turn_id: turn };
    },
    abort: (id) => { counters.aborted++; counters.changed(); return sessionsApi.abort(id); },
    answerDialog: async (id, dialog, answer) => { await sessionsApi.answerDialog(id, dialog, answer); counters.changed(); },
  },
};

const emit = (type: string, payload: unknown, live = false) => sessionsApi.emit(ID, type, payload, live);
const inject = async (seconds: number) => {
  await microphone.resume();
  const source = microphone.createBufferSource();
  source.buffer = await microphone.decodeAudioData(await (await fetch("/test-speech.wav")).arrayBuffer());
  source.connect(destination);
  source.start(0, 0, seconds);
};

function Harness() {
  const [mounted, setMounted] = useState(true);
  const [, render] = useState(0);
  useEffect(() => { counters.changed = () => render((n) => n + 1); }, []);
  const tracks = () => destination.stream.getTracks().map((t) => `${t.readyState}:${t.enabled}`).join(",");
  const [checked, setChecked] = useState({ tracks: "", requests: "" });
  return (
    <>
      <div style={{ display: "flex", justifyContent: "center", gap: 16 }}><ThemeSwitcher /></div>
      <main data-testid="workspace" style={{ display: "flex", flexDirection: "column", maxWidth: 980, height: "calc(100vh - 120px)", minHeight: 540, margin: "16px auto 0" }}>
        {mounted && (
          <MemoryRouter initialEntries={[`/sessions/${ID}`]}>
            <Routes><Route path="/sessions/:id" element={<ChatPage />} /></Routes>
          </MemoryRouter>
        )}
      </main>
      <aside style={{ display: "flex", flexWrap: "wrap", gap: 10, fontSize: 10, padding: 8 }}>
        <button onClick={() => setMounted(false)}>Unmount workspace</button>
        <button onClick={() => { for (const track of destination.stream.getTracks()) { track.stop(); track.dispatchEvent(new Event("ended")); } }}>Disconnect microphone</button>
        <button onClick={() => void inject(0.8)}>Inject short speech</button>
        <button onClick={() => void inject(2.5)}>Inject speech</button>
        <button onClick={() => { emit("portal_status", { status: "running" }); emit("message_update", { streamId: "m9", assistantMessageEvent: { type: "text_delta", delta: "Here is the first sentence. More" } }, true); }}>Stream reply</button>
        <button onClick={() => { emit("message_update", { streamId: "m9", assistantMessageEvent: { type: "text_delta", delta: " text follows." } }, true); emit("message_end", { streamId: "m9", message: { role: "assistant", content: [{ type: "text", text: "Here is the first sentence. More text follows." }] } }); emit("portal_status", { status: "idle" }); }}>Finish reply</button>
        <button onClick={() => { emit("portal_status", { status: "running" }); emit("tool_execution_start", { toolName: "bash", toolCallId: "terminal-demo", args: { command: "npm run build" } }); }}>Use terminal</button>
        <button onClick={() => { emit("portal_status", { status: "running" }); emit("portal_prefill", { total: 40000, processed: 8000, cache: 8000, timeMs: 10 }, true); }}>Show prefill</button>
        <button onClick={() => { emit("portal_status", { status: "running" }); emit("compaction_start", {}); }}>Start compaction</button>
        <button onClick={() => { emit("compaction_end", {}); emit("portal_status", { status: "idle" }); }}>End compaction</button>
        <button onClick={() => emit("extension_ui_request", { id: "choice", method: "select", title: "Elige el siguiente paso", options: ["Revisar cambios", "Correr pruebas"] }, true)}>Show options</button>
        <span data-testid="voice-send">{String(counters.voice)}</span>
        <span data-testid="sent">{counters.sent}</span>
        <span data-testid="aborted">{counters.aborted}</span>
        <span data-testid="selected">{sessionsApi.answered.length}</span>
        <button onClick={() => setChecked({ tracks: tracks(), requests: String(micRequests) })}>Check mic tracks</button>
        <span data-testid="tracks">{checked.tracks}</span><span data-testid="mic-requests">{checked.requests}</span>
      </aside>
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <PortsProvider ports={ports}><IsAdminContext.Provider value={true}><AppearanceProvider isAdmin><Harness /></AppearanceProvider></IsAdminContext.Provider></PortsProvider>,
);
