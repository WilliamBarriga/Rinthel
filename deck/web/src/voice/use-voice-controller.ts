import { useEffect, useReducer, useRef } from "react";
import type { TranscriptItem } from "../chat/model/transcript";
import { useVoiceProfiling, type VoiceEvent } from "./use-voice-profiling";
import { useVoiceSounds } from "./use-voice-sounds";
import { initialVoiceSession, voiceSessionReducer, type VoiceLevels } from "./model/voice-session";
import { useVoiceConfig } from "./use-voice-config";
import { useVoicePlayback } from "./use-voice-playback";
import { useMicSession } from "./use-mic-session";

export interface VoiceControllerOptions {
  sessionId: string;
  items: TranscriptItem[];
  running: boolean;
  /** Whether the Agent is compacting the conversation now, and how the last compaction ended. */
  compaction: { active: boolean; completed: boolean };
  /** The Session's recent events: tool activity and the profiler's marks. */
  events: VoiceEvent[];
  onModeChange(active: boolean): void;
  onSend(text: string, options?: { voice?: boolean }): Promise<void>;
  onAbort(): Promise<void>;
}

/** Puts the voice session together: settings, playback and the microphone; rendering lives in `VoiceControl`. */
export function useVoiceController({ sessionId, items, running, compaction, events, onSend, onAbort, onModeChange }: VoiceControllerOptions) {
  const profile = useVoiceProfiling(events);
  const sounds = useVoiceSounds();
  const [state, dispatch] = useReducer(voiceSessionReducer, initialVoiceSession);
  const { phase, error, muted, transcript, speaking } = state;
  const enabled = state.status === "active";
  const starting = state.status === "starting";
  const levels = useRef<VoiceLevels>({ input: 0, output: 0 });
  const startButton = useRef<HTMLButtonElement>(null);
  const compacting = running && compaction.active;
  // Read by the detector and the engine long after the render that made them: always the latest props.
  const input = useRef({ items, running, onSend, onAbort, compacting });
  input.current = { items, running, onSend, onAbort, compacting };
  const { settings, latest: currentSettings } = useVoiceConfig(() => mic.stop());
  const synthesize = useVoicePlayback({
    sessionId, levels, profiling: profile.profiling, profiler: profile.profiler,
    sequential: () => currentSettings.current.sequential,
    onSpeaking: (value) => dispatch({ type: "read", reading: { speaking: value } }),
  });
  const mic = useMicSession({ sessionId, starting, settings: currentSettings, input, dispatch, levels, profile, sounds, synthesize });
  useEffect(() => {
    mic.engine.current?.setCompacting(compacting, compaction.completed);
    mic.engine.current?.observe(items);
    if (compacting) mic.transcription.current?.discard();
  }, [items, running, compacting, compaction.completed]);
  useEffect(() => {
    onModeChange(enabled || starting);
    return () => onModeChange(false);
  }, [enabled, starting, onModeChange]);
  const endMode = () => {
    mic.stop();
    requestAnimationFrame(() => startButton.current?.focus({ preventScroll: true }));
  };
  return {
    available: settings.available, enabled, starting, phase, error, muted, transcript, speaking,
    sounds: sounds.sounds, toggleSounds: sounds.toggleSounds, cue: sounds.cue, levels,
    toggleMute: mic.toggleMute, endMode, start: mic.start, startButton,
    profileOpen: profile.profileOpen, profiler: profile.profiler,
    comparison: settings.comparison, sequentialMode: settings.sequential, sentenceMode: settings.sentenceChunks, prefetchMode: settings.ttsPrefetch,
    toggleProfile: profile.toggleProfile, closeProfile: profile.closeProfile,
  };
}
