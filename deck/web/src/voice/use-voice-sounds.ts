import { useCallback, useRef, useState } from "react";
import { voiceCue, type VoiceCue } from "./voice-cues";

/** Cue sounds: the persisted on/off toggle and the cue player on the session's AudioContext. */
export function useVoiceSounds() {
  const [sounds, setSounds] = useState(() => localStorage.getItem('voiceSounds') !== 'off');
  const soundsEnabled = useRef(sounds); soundsEnabled.current = sounds;
  const soundContext = useRef<AudioContext | null>(null);
  const cue = useCallback((kind: VoiceCue) => { if (soundsEnabled.current && soundContext.current) voiceCue(soundContext.current, kind); }, []);
  const toggleSounds = () => setSounds(value => { localStorage.setItem('voiceSounds', value ? 'off' : 'on'); return !value; });
  return { sounds, toggleSounds, soundsEnabled, soundContext, cue };
}
