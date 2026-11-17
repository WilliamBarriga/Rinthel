import type { VoicePhase } from "../hands-free";

export interface VoiceLevels { input: number; output: number }

/** One lifecycle state replaces independent enabled/starting/session-active flags. */
export interface VoiceSessionState {
  status: "off" | "starting" | "active";
  phase: VoicePhase;
  muted: boolean;
  speaking: boolean;
  transcript: string;
  error: string;
}
export const initialVoiceSession: VoiceSessionState = {
  status: "off", phase: "Escuchando", muted: false, speaking: false, transcript: "", error: "",
};
/** What the live session reports while it runs: ignored once the session is off. */
export type VoiceSessionReading = Partial<Pick<VoiceSessionState, "phase" | "muted" | "speaking" | "transcript" | "error">>;
export type VoiceSessionEvent =
  | { type: "start" }
  | { type: "started" }
  | { type: "stop" }
  | { type: "read"; reading: VoiceSessionReading }
  /** A failure is kept even after the session ended, so the start button can show it. */
  | { type: "error"; value: string };

/** Lifecycle transitions do not acquire or release media resources. The controller does. */
export function voiceSessionReducer(state: VoiceSessionState, event: VoiceSessionEvent): VoiceSessionState {
  switch (event.type) {
    case "start": return state.status !== "off" ? state : { ...state, status: "starting", error: "", muted: false };
    case "started": return state.status !== "starting" ? state : { ...state, status: "active" };
    case "stop": return state.status === "off" ? state : { ...initialVoiceSession, phase: state.phase, error: state.error };
    case "read": return state.status === "off" ? state : { ...state, ...event.reading };
    case "error": return { ...state, error: event.value };
  }
}
