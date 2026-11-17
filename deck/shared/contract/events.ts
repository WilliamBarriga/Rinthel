/**
 * What a Session's event stream (`GET /api/sessions/:id/events`, SSE) carries. pi's own events
 * (`message_update`, `message_end`, `tool_execution_*`, `agent_start`, `agent_settled`…) go through as
 * pi emits them; the ones Deck adds are named `portal_*` and typed here.
 */

/** One event as the stream sends it. A negative `seq` is live only (never stored, never a cursor). */
export interface SessionEvent {
  seq: number;
  type: string;
  /** When it happened, in epoch milliseconds. */
  at?: number;
  payload: unknown;
}

/** `portal_prompt`: what the person sent, as they wrote it (any framing Deck adds for the model is not here). */
export interface PromptEvent {
  message: string;
  turn_id: string;
}

/** `portal_status`: the Session's state moved. */
export interface StatusEvent {
  status: "idle" | "running" | "error" | "interrupted";
  error?: string;
  aborted?: boolean;
}

/** `portal_notice`: something Deck says into the transcript. */
export interface NoticeEvent {
  text: string;
  error?: boolean;
}

/** `portal_prefill` (live only): how far llama-server has got through the prompt. */
export interface PrefillEvent {
  total: number;
  /** Already in the KV cache: the part that does not have to be processed again. */
  cache: number;
  processed: number;
  timeMs: number;
}

/** `portal_route` (live only): the Local model the Session talks to now, or none. */
export interface RouteEvent {
  model: string | null;
  context_window: number | null;
}

/** `portal_guard`: a call the Guard stopped. */
export interface GuardNotice {
  tool: string;
  verdict: "allow" | "deny";
  reason: string;
}

/** `GET /api/sessions/:id/config`: the composer's pills. `stats` is null until pi runs. */
export interface SessionConfig {
  live: boolean;
  state: { model: { id: string; name: string; provider: string; contextWindow?: number }; thinkingLevel: string };
  thinking: { levels: string[] };
  stats: { contextUsage: { tokens: number; contextWindow: number; percent: number } } | null;
}

/** `POST /api/sessions/:id/prompt`: pi took the message; `queued` when it waits behind a run in course. */
export interface PromptAccepted {
  ok: true;
  status: "running";
  queued: boolean;
  turn_id: string;
}
