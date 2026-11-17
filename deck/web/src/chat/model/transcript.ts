import type { SessionEvent, SessionStatus, PrefillEvent } from "@deck/contract";

/**
 * The transcript of a Session as the chat shows it, folded from its event stream: what the person
 * wrote, what the Agent answered (streamed, then final), the tools it ran, what Deck and the Guard
 * said, and the dialogs an extension waits on. Pure: the controller feeds it the events in order.
 */
export type TranscriptItem =
  | { kind: "user"; id: string; text: string }
  | { kind: "assistant"; id: string; text: string; thinking: string; streaming: boolean }
  | { kind: "tool"; id: string; name: string; detail: string; status: "running" | "done" | "error"; output: string }
  | { kind: "notice"; id: string; text: string; error: boolean }
  | { kind: "guard"; id: string; tool: string; reason: string };

export interface UiDialog {
  id: string;
  method: "select" | "confirm" | "input" | "editor";
  title: string;
  message?: string;
  options?: string[];
}

export interface Transcript {
  items: TranscriptItem[];
  status: SessionStatus | "unknown";
  /** How far llama-server has got through the prompt, while it reads it. */
  prefill: PrefillEvent | null;
  /** The Local model the Session talks to now, as the stream last said. */
  route: { model: string | null; contextWindow: number | null } | null;
  dialogs: UiDialog[];
  /** The last stored event folded in: a replayed one at or before it is skipped. */
  lastSeq: number;
}

export const emptyTranscript: Transcript = { items: [], status: "unknown", prefill: null, route: null, dialogs: [], lastSeq: 0 };

type Block = { type?: string; text?: string; thinking?: string };

const textOf = (content: unknown, kind: "text" | "thinking"): string =>
  Array.isArray(content) ? (content as Block[]).filter((b) => b?.type === kind).map((b) => b[kind] ?? "").join("") : "";

const summarize = (args: unknown): string => {
  if (!args || typeof args !== "object") return "";
  const a = args as Record<string, unknown>;
  const first = a.command ?? a.path ?? a.file_path ?? a.pattern ?? a.query;
  const text = typeof first === "string" ? first : JSON.stringify(args);
  return text.length > 120 ? `${text.slice(0, 119)}…` : text;
};

function upsert(items: TranscriptItem[], item: TranscriptItem): TranscriptItem[] {
  const at = items.findIndex((i) => i.kind === item.kind && i.id === item.id);
  if (at < 0) return [...items, item];
  const next = items.slice();
  next[at] = item;
  return next;
}

/** A stream event that is not a stored row: the server's `live-reset` before a replay drops what was only streaming. */
export type StreamSignal = { type: "live-reset" };

export function foldEvent(state: Transcript, event: SessionEvent | StreamSignal): Transcript {
  if (!("seq" in event)) {
    return { ...state, items: state.items.filter((i) => !(i.kind === "assistant" && i.streaming)), prefill: null };
  }
  if (event.seq > 0) {
    if (event.seq <= state.lastSeq) return state;
    state = { ...state, lastSeq: event.seq };
  }
  const p = (event.payload ?? {}) as Record<string, any>;
  const key = String(event.seq);
  switch (event.type) {
    case "portal_prompt":
      return { ...state, items: [...state.items, { kind: "user", id: String(p.turn_id ?? key), text: String(p.message ?? "") }] };
    case "portal_status":
      return { ...state, status: p.status, prefill: p.status === "running" ? state.prefill : null,
        items: p.status === "error" && p.error ? [...state.items, { kind: "notice", id: key, text: String(p.error), error: true }] : state.items };
    case "portal_notice":
      return { ...state, items: [...state.items, { kind: "notice", id: key, text: String(p.text ?? ""), error: Boolean(p.error) }] };
    case "portal_guard":
      // Every call the Guard checked is in the log; only a refusal is a line of the conversation.
      if (p.verdict !== "deny") return state;
      return { ...state, items: [...state.items, { kind: "guard", id: key, tool: String(p.tool ?? ""), reason: String(p.reason ?? "") }] };
    case "portal_prefill":
      return { ...state, prefill: { total: p.total, cache: p.cache, processed: p.processed, timeMs: p.timeMs } };
    case "portal_route":
      return { ...state, route: { model: p.model ?? null, contextWindow: p.context_window ?? null } };
    case "message_update": {
      const delta = p.assistantMessageEvent ?? {};
      const id = String(p.streamId ?? "stream");
      const current = state.items.find((i): i is Extract<TranscriptItem, { kind: "assistant" }> => i.kind === "assistant" && i.id === id)
        ?? { kind: "assistant" as const, id, text: "", thinking: "", streaming: true };
      const text = delta.type === "text_delta" ? current.text + (delta.delta ?? "") : current.text;
      const thinking = delta.type === "thinking_delta" ? current.thinking + (delta.delta ?? "") : current.thinking;
      return { ...state, prefill: null, items: upsert(state.items, { ...current, text, thinking, streaming: true }) };
    }
    case "message_snapshot":
      return { ...state, items: upsert(state.items, {
        kind: "assistant", id: String(p.streamId), text: textOf(p.message?.content, "text"), thinking: textOf(p.message?.content, "thinking"), streaming: true,
      }) };
    case "message_end": {
      if (p.message?.role !== "assistant") return state;
      const text = textOf(p.message.content, "text");
      const thinking = textOf(p.message.content, "thinking");
      const failure = p.message.stopReason === "error" && p.message.errorMessage ? String(p.message.errorMessage) : null;
      let items = state.items;
      if (text || thinking) items = upsert(items, { kind: "assistant", id: String(p.streamId ?? key), text, thinking, streaming: false });
      else items = items.filter((i) => !(i.kind === "assistant" && i.id === p.streamId));
      if (failure) items = [...items, { kind: "notice", id: `${key}-error`, text: failure, error: true }];
      return { ...state, prefill: null, items };
    }
    case "tool_execution_start":
      return { ...state, items: upsert(state.items, {
        kind: "tool", id: String(p.toolCallId ?? key), name: String(p.toolName ?? "tool"), detail: summarize(p.args), status: "running", output: "",
      }) };
    case "tool_execution_end": {
      const id = String(p.toolCallId ?? key);
      const before = state.items.find((i) => i.kind === "tool" && i.id === id) as Extract<TranscriptItem, { kind: "tool" }> | undefined;
      return { ...state, items: upsert(state.items, {
        kind: "tool", id, name: String(p.toolName ?? before?.name ?? "tool"), detail: before?.detail ?? "",
        status: p.isError ? "error" : "done", output: textOf(p.result?.content, "text"),
      }) };
    }
    case "agent_settled":
      return { ...state, prefill: null };
    case "extension_ui_request":
      if (p.method === "notify") return { ...state, items: [...state.items, { kind: "notice", id: String(p.id), text: String(p.message ?? ""), error: p.notifyType === "error" }] };
      if (!["select", "confirm", "input", "editor"].includes(p.method)) return state;
      return { ...state, dialogs: [...state.dialogs, { id: String(p.id), method: p.method, title: String(p.title ?? ""), message: p.message, options: p.options }] };
    case "extension_ui_cancel":
      return { ...state, dialogs: state.dialogs.filter((d) => d.id !== p.id) };
    default:
      return state;
  }
}

/** A dialog the person answered goes away at once; the server takes the answer. */
export function dropDialog(state: Transcript, id: string): Transcript {
  return { ...state, dialogs: state.dialogs.filter((d) => d.id !== id) };
}

/** Whether the Agent is working: the composer shows Stop instead of Send. */
export const isBusy = (state: Transcript): boolean => state.status === "running";

/** "12.3k / 64k": what the Session has used of the Local model's window, when both are known. */
export function windowLabel(used: number | null, contextWindow: number | null): string | null {
  if (!contextWindow) return null;
  const k = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10_000 ? 0 : 1)}k` : String(n));
  return used === null ? `${k(contextWindow)} de contexto` : `${k(used)} / ${k(contextWindow)}`;
}
