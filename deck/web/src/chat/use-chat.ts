import { useCallback, useEffect, useReducer, useState } from "react";
import type { Session, SessionConfig } from "@deck/contract";
import { useSessionsApi } from "../ports/context";
import { messageOf } from "../ports/http-errors";
import { dropDialog, emptyTranscript, foldEvent, isBusy, type Transcript } from "./model/transcript";
import type { StreamEvent } from "../ports/sessions";

type Action = { type: "event"; event: StreamEvent } | { type: "answered"; id: string } | { type: "reset" };

function reducer(state: Transcript, action: Action): Transcript {
  if (action.type === "reset") return emptyTranscript;
  if (action.type === "answered") return dropDialog(state, action.id);
  return foldEvent(state, action.event);
}

/**
 * Controller of one Session's chat: its row, its transcript (the event stream folded by
 * `transcript.ts`), sending and stopping, the extension dialogs, and the context used once pi runs.
 * A send the server refuses (an owner gone, no Local model, a daemon down) stays as `error`.
 */
export function useChat(id: string, { onFailure }: { onFailure?: (error: unknown) => void } = {}) {
  const api = useSessionsApi();
  const [transcript, dispatch] = useReducer(reducer, emptyTranscript);
  const [session, setSession] = useState<Session | null>(null);
  const [config, setConfig] = useState<SessionConfig | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    dispatch({ type: "reset" });
    setSession(null);
    setConfig(null);
    api.get(id).then(setSession, (e) => { onFailure?.(e); setError(messageOf(e)); });
    const subscription = api.events(id, (event) => dispatch({ type: "event", event }));
    return () => subscription.close();
  }, [api, id]);

  const busy = isBusy(transcript);
  // The context used is known once pi runs; read again whenever a turn ends.
  useEffect(() => {
    if (busy) return;
    let current = true;
    api.config(id).then((c) => { if (current) setConfig(c); }, () => {});
    return () => { current = false; };
  }, [api, id, busy, transcript.items.length]);

  const [draft, setDraft] = useState("");
  /** Sends the draft; it is cleared once pi took it, and kept with the refusal otherwise. */
  const send = useCallback(async (): Promise<void> => {
    const message = draft.trim();
    if (!message) return;
    setError(null);
    try {
      await api.prompt(id, message);
      setDraft("");
    } catch (e) {
      onFailure?.(e);
      setError(messageOf(e));
    }
  }, [api, id, draft, onFailure]);

  const stop = useCallback(async () => {
    try { await api.abort(id); } catch (e) { setError(messageOf(e)); }
  }, [api, id]);

  const answer = useCallback(async (dialog: string, response: { value?: unknown; cancelled?: boolean }) => {
    dispatch({ type: "answered", id: dialog });
    try { await api.answerDialog(id, dialog, response); } catch (e) { setError(messageOf(e)); }
  }, [api, id]);

  const used = config?.stats?.contextUsage.tokens ?? null;
  const contextWindow = transcript.route?.contextWindow ?? config?.state.model.contextWindow ?? null;
  return { session, transcript, busy, error, draft, setDraft, send, stop, answer, used, window: contextWindow };
}
