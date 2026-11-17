import type { VoicePhase } from "../hands-free";

/**
 * One turn of the hands-free engine as a single value. These replace the engine's
 * `alive`, `hearing`, `compactionSpeech`, `processing` and `sending` flags: only the
 * combinations below can exist. `muted`, `acceptingReplies` and `thinkingAnnounced`
 * are policy of the engine, not phase, and stay with it.
 */
export interface TurnState {
  life: "alive" | "stopped";
  /** What the microphone is doing: hearing the user, or the user talking over a compaction. */
  input: "idle" | "hearing" | "over-compaction";
  /** What the engine does with the user's words. A send always happens inside a transcription. */
  work: "idle" | "transcribing" | "sending";
  compacting: boolean;
  /** Set by `speech-end`: the speech was a real turn, so the engine should transcribe it. */
  takesTurn: boolean;
}
export const idleTurn: TurnState = { life: "alive", input: "idle", work: "idle", compacting: false, takesTurn: false };

export type TurnEvent =
  | { type: "speech-start" }
  | { type: "speech-end" }
  | { type: "mute" }
  | { type: "compacting"; active: boolean }
  | { type: "transcribe-start" }
  | { type: "send-start" }
  | { type: "send-end" }
  | { type: "transcribe-end" }
  | { type: "stop" };

export function turnAfter(state: TurnState, event: TurnEvent): TurnState {
  if (state.life === "stopped") return state;
  const next = { ...state, takesTurn: false };
  switch (event.type) {
    case "speech-start": return { ...next, input: state.compacting ? "over-compaction" : "hearing" };
    case "speech-end":
      if (state.compacting || state.input === "over-compaction") return { ...next, input: state.input === "over-compaction" ? "idle" : state.input };
      return { ...next, input: "idle", takesTurn: true };
    case "mute": return { ...next, input: state.input === "hearing" ? "idle" : state.input };
    case "compacting": return { ...next, compacting: event.active };
    case "transcribe-start": return { ...next, work: "transcribing" };
    case "send-start": return { ...next, work: "sending" };
    case "send-end": return { ...next, work: "transcribing" };
    case "transcribe-end": return { ...next, work: "idle" };
    case "stop": return { ...next, life: "stopped" };
  }
}

/** What the user sees: the most urgent thing first. */
export function displayPhase(turn: TurnState, { speaking, agentRunning }: { speaking: boolean; agentRunning: boolean }): VoicePhase {
  if (turn.input === "hearing") return "Te escucho";
  if (turn.compacting) return "Compactando el contexto";
  if (turn.work === "transcribing") return "Transcribiendo";
  if (speaking) return "Hablando";
  return agentRunning || turn.work === "sending" ? "Pensando" : "Escuchando";
}

/** The one place that decides a reply must wait: a sequential run speaks only once the agent is done. */
export function holdsOutput({ sequential, sentenceChunks }: { sequential?: boolean; sentenceChunks?: boolean }, agentRunning: boolean): boolean {
  return Boolean(sequential) && !sentenceChunks && agentRunning;
}
