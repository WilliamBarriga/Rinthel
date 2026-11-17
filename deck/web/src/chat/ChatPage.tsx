import { useState, type FormEvent, type KeyboardEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { LuArrowLeft, LuArrowUp, LuSquare } from "react-icons/lu";
import { useReportExpired } from "../failure-context";
import { useIsAdmin } from "../auth/use-is-admin";
import { ModelPicker } from "../models/ModelPicker";
import { useActiveModel } from "../models/use-local-model";
import { CanvasPanel } from "../canvas/CanvasPanel";
import { SessionBrowser } from "./SessionBrowser";
import { useChat } from "./use-chat";
import { VoiceControl } from "../voice/VoiceControl";
import type { WorkPhase } from "../voice/ActivityProgress";
import type { VoiceEvent } from "../voice/use-voice-profiling";
import { windowLabel, type TranscriptItem, type UiDialog } from "./model/transcript";

/** One Session's chat: the transcript, llama-server's prefill progress, and the composer. */
export function ChatPage() {
  const { id = "" } = useParams();
  const [canvasOpen, setCanvasOpen] = useState(false);
  const navigate = useNavigate();
  const isAdmin = useIsAdmin();
  const reportExpired = useReportExpired();
  const chat = useChat(id, { onFailure: reportExpired });
  const active = useActiveModel();
  const model = chat.transcript.route?.model ?? active.model;
  const contextWindow = chat.window ?? active.contextWindow;
  const prefill = chat.transcript.prefill;
  const [stage, setStage] = useState<HTMLDivElement | null>(null);
  const [voiceMode, setVoiceMode] = useState(false);
  const compaction = chat.transcript.compaction;
  const workPhase: WorkPhase | null = chat.busy && compaction.active ? { kind: "compacting", since: compaction.since }
    : prefill && prefill.total > 0 ? { kind: "processing", prefill } : null;

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    void chat.send();
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  };

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <header className="flex items-center gap-3 border-b border-line px-5 py-3">
        <button type="button" aria-label="Volver a Sesiones" onClick={() => navigate("/")} className="rounded-lg p-1 text-fg-muted hover:bg-fg/5"><LuArrowLeft className="h-4 w-4" /></button>
        <div className="min-w-0">
          <h1 className="truncate text-sm font-semibold text-fg">{chat.session?.title ?? "Sesión"}</h1>
          <p className="truncate text-xs text-fg-subtle">{chat.session?.kind === "task" ? chat.session.workspace : "Chat con el Agente"}</p>
        </div>
      </header>
      <CanvasPanel sessionId={id} open={canvasOpen} setOpen={setCanvasOpen} />

      <div className="flex min-h-0 flex-1">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      {/* Voice mode takes the chat's place: the stage goes here, the dialogs stay below it. */}
      <div ref={setStage} className={voiceMode ? "flex min-h-0 flex-1 flex-col" : "hidden"} />
      {voiceMode && chat.transcript.dialogs.length > 0 && (
        <div className="space-y-3 px-5 py-3">{chat.transcript.dialogs.map((d) => <Dialog key={d.id} dialog={d} onAnswer={(r) => void chat.answer(d.id, r)} />)}</div>
      )}

      <section aria-label="Transcripción" hidden={voiceMode} className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
        {chat.transcript.items.length === 0 && <p className="text-sm text-fg-subtle">Escribe para empezar.</p>}
        {chat.transcript.items.map((item) => <Item key={`${item.kind}-${item.id}`} item={item} />)}
        {prefill && prefill.total > 0 && (
          <div role="status" className="text-xs text-fg-subtle">
            Leyendo el contexto: {Math.round(((prefill.cache + prefill.processed) / prefill.total) * 100)}% ({prefill.total} tokens, {prefill.cache} en caché)
          </div>
        )}
        {chat.transcript.dialogs.map((d) => <Dialog key={d.id} dialog={d} onAnswer={(r) => void chat.answer(d.id, r)} />)}
      </section>

      <form onSubmit={submit} hidden={voiceMode} className="border-t border-line px-5 py-3">
        {chat.error && <p role="alert" className="mb-2 text-xs text-red-500">{chat.error}</p>}
        <div className="prompt-shell">
          <textarea
            aria-label="Mensaje"
            className="prompt-input"
            placeholder="Escribe un mensaje…"
            value={chat.draft}
            onChange={(e) => chat.setDraft(e.target.value)}
            onKeyDown={onKey}
          />
          <div className="composer-toolbar">
            <div className="composer-settings gap-3 text-xs text-fg-subtle">
              <span title="Local model">{model ?? "sin Local model"}</span>
              {windowLabel(chat.used, contextWindow) && <span title="Ventana de contexto">{windowLabel(chat.used, contextWindow)}</span>}
              {isAdmin && <ModelPicker compact onSwitched={() => void active.refresh()} />}
            </div>
            <div className="composer-actions">
              <VoiceControl
                sessionId={id} title={chat.session?.title ?? "Sesión"} stageTarget={stage} workPhase={workPhase}
                items={chat.transcript.items} running={chat.busy} compaction={chat.transcript.compaction} events={chat.events as VoiceEvent[]}
                onModeChange={setVoiceMode} onSend={chat.sendVoice} onAbort={chat.stop}
              />
              {chat.busy ? (
                <button type="button" aria-label="Detener" className="prompt-action prompt-stop" onClick={() => void chat.stop()}><LuSquare /></button>
              ) : (
                <button type="submit" aria-label="Enviar" className="prompt-action prompt-send" disabled={!chat.draft.trim()}><LuArrowUp /></button>
              )}
            </div>
          </div>
        </div>
      </form>
      </div>
      {isAdmin && <SessionBrowser key={id} sessionId={id} onFailure={reportExpired} />}
      </div>
    </div>
  );
}

function Item({ item }: { item: TranscriptItem }) {
  switch (item.kind) {
    case "user":
      return <div className="ml-auto max-w-[80%] whitespace-pre-wrap rounded-xl bg-fg/5 px-3 py-2 text-sm text-fg">{item.text}</div>;
    case "assistant":
      return (
        <article aria-label="Respuesta del Agente" className="max-w-[90%] text-sm text-fg">
          {item.thinking && (
            <details className="mb-1 text-xs text-fg-subtle"><summary>Razonamiento</summary><p className="whitespace-pre-wrap">{item.thinking}</p></details>
          )}
          <p className="whitespace-pre-wrap">{item.text}{item.streaming ? "…" : ""}</p>
        </article>
      );
    case "tool":
      return (
        <details className="rounded-lg border border-line px-3 py-1 text-xs text-fg-muted">
          <summary>{item.name} {item.detail} <span className="text-fg-subtle">({item.status === "running" ? "en curso" : item.status === "error" ? "falló" : "listo"})</span></summary>
          {item.output && <pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap">{item.output}</pre>}
        </details>
      );
    case "guard":
      return <p role="note" className="rounded-lg border border-amber-500/40 px-3 py-2 text-xs text-fg-muted">El Guard detuvo {item.tool}: {item.reason}</p>;
    case "notice":
      return <p className={`text-xs ${item.error ? "text-red-500" : "text-fg-subtle"}`}>{item.text}</p>;
  }
}

function Dialog({ dialog, onAnswer }: { dialog: UiDialog; onAnswer: (r: { value?: unknown; cancelled?: boolean }) => void }) {
  const [text, setText] = useState("");
  return (
    <div role="dialog" aria-label={dialog.title} className="ui-card space-y-2 text-sm">
      <p className="font-medium text-fg">{dialog.title}</p>
      {dialog.message && <p className="text-fg-muted">{dialog.message}</p>}
      {dialog.method === "select" && (dialog.options ?? []).map((o) => (
        <button key={o} type="button" onClick={() => onAnswer({ value: o })} className="mr-2 rounded-lg border border-line px-2 py-1 text-xs">{o}</button>
      ))}
      {dialog.method === "confirm" && (
        <button type="button" onClick={() => onAnswer({ value: true })} className="mr-2 rounded-lg border border-line px-2 py-1 text-xs">Sí</button>
      )}
      {(dialog.method === "input" || dialog.method === "editor") && (
        <>
          <input aria-label={dialog.title} value={text} onChange={(e) => setText(e.target.value)} className="w-full rounded-lg border border-line bg-canvas px-2 py-1" />
          <button type="button" onClick={() => onAnswer({ value: text })} className="mr-2 rounded-lg border border-line px-2 py-1 text-xs">Aceptar</button>
        </>
      )}
      <button type="button" onClick={() => onAnswer({ cancelled: true })} className="rounded-lg px-2 py-1 text-xs text-fg-muted">Cancelar</button>
    </div>
  );
}
