import { useCallback, useRef } from "react";
import { api } from "./api";

/** Calcado de use-notification-sound.ts: one shared element, try/catch around autoplay. */
export function useTextToSpeech() {
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const speak = useCallback(async (text: string, lang?: string) => {
    if (!text.trim()) return;
    try {
      const blob = await api.speak(text, lang);
      const url = URL.createObjectURL(blob);
      let audio = audioRef.current;
      if (!audio) {
        audio = new Audio();
        audioRef.current = audio;
      }
      audio.src = url;
      audio.onended = () => URL.revokeObjectURL(url);
      await audio.play();
    } catch {
      // Autoplay bloqueado, TTS caído, o texto vacío — silencioso, igual que el sonido de notificación.
    }
  }, []);

  return { speak };
}
