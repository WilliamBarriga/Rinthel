import { useCallback, useRef } from "react";

export type SoundType = "default" | "chime" | "pop" | "futuristic" | "interface-zoom" | "none";

const SOUND_URLS: Record<string, string> = {
  futuristic: "/sounds/futuristic.wav",
  "interface-zoom": "/sounds/interface-zoom.wav",
};

export function useNotificationSound(enabled: boolean, type: SoundType) {
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const play = useCallback(() => {
    if (!enabled || type === "none") return;

    // Custom audio files — reuse the same element to prevent overlap
    if (type in SOUND_URLS) {
      try {
        let audio = audioRef.current;
        if (!audio) {
          audio = new Audio(SOUND_URLS[type]);
          audioRef.current = audio;
        } else {
          audio.currentTime = 0;
        }
        void audio.play();
      } catch {
        // Autoplay bloqueado o error de carga
      }
      return;
    }

    // Generated tones via Web Audio API
    try {
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();

      const oscillator = ctx.createOscillator();
      const gain = ctx.createGain();
      oscillator.connect(gain);
      gain.connect(ctx.destination);

      if (type === "default") {
        // Dos tonos ascendentes (ding-dong)
        oscillator.frequency.setValueAtTime(523, ctx.currentTime);       // C5
        oscillator.frequency.setValueAtTime(659, ctx.currentTime + 0.15); // E5
      } else if (type === "chime") {
        // Un tono largo suave
        oscillator.frequency.setValueAtTime(880, ctx.currentTime);       // A5
        gain.gain.setValueAtTime(0.2, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);
      } else if (type === "pop") {
        // Click corto
        oscillator.frequency.setValueAtTime(1200, ctx.currentTime);
        gain.gain.setValueAtTime(0.4, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.15);
      }

      gain.gain.setValueAtTime(0.25, ctx.currentTime);
      oscillator.start(ctx.currentTime);
      oscillator.stop(ctx.currentTime + (type === "chime" ? 0.6 : 0.3));
    } catch {
      // AudioContext puede fallar en contextos no seguros
    }
  }, [enabled, type]);

  return play;
}
