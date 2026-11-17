import { useEffect, useRef, useState } from "react";
import type { VoiceVad } from "@deck/contract";
import { useVoiceSpeech } from "../ports/context";
import { DEFAULT_VAD } from "./vad";

/** What the reader's voice settings and the Instance say about voice in a Session. */
export interface VoiceSettings {
  /** The reader turned voice on and the Instance has both `stt` and `tts` active. */
  available: boolean;
  statusSpeech: boolean;
  comparison: boolean;
  sequential: boolean;
  sentenceChunks: boolean;
  ttsPrefetch: boolean;
  vad: VoiceVad;
}

const UNAVAILABLE: VoiceSettings = { available: false, statusSpeech: true, comparison: false, sequential: false, sentenceChunks: false, ttsPrefetch: false, vad: DEFAULT_VAD };

/** Fired by the Voz screen after a save, so an open Session reads the settings again. */
export const VOICE_SETTINGS_CHANGED = "voice-settings-changed";

/**
 * Reads the voice settings, and again whenever the Voz screen saves them. Without an active `stt`
 * or `tts` voice is not offered at all: no error, nothing to show. `latest` is the same object
 * `settings` holds, readable from callbacks that outlive a render.
 */
export function useVoiceConfig(onUnavailable: () => void) {
  const speech = useVoiceSpeech();
  const [settings, setSettings] = useState(UNAVAILABLE);
  const latest = useRef(settings); latest.current = settings;
  const unavailable = useRef(onUnavailable); unavailable.current = onUnavailable;
  useEffect(() => {
    let mounted = true;
    const load = () => speech.settings().then((config) => {
      if (!mounted) return;
      const available = config.enabled && config.stt && config.tts;
      setSettings({
        available,
        statusSpeech: config.statusSpeech !== false,
        comparison: config.comparison === true,
        sequential: config.pipelineMode === "sequential",
        sentenceChunks: config.sentenceChunks === true,
        ttsPrefetch: config.ttsPrefetch === true,
        vad: { ...DEFAULT_VAD, ...config.vad },
      });
      if (!available) unavailable.current();
    }).catch(() => { if (mounted) { setSettings(UNAVAILABLE); unavailable.current(); } });
    void load();
    window.addEventListener(VOICE_SETTINGS_CHANGED, load);
    return () => { mounted = false; window.removeEventListener(VOICE_SETTINGS_CHANGED, load); };
  }, [speech]);
  return { settings, latest };
}
