import type { VoiceVad } from "@deck/contract";

/** What speech detection starts from; the server fills the same values in for a field never saved. */
export const DEFAULT_VAD: VoiceVad = { positiveSpeechThreshold: 0.65, negativeSpeechThreshold: 0.35, minSpeechMs: 256, preSpeechPadMs: 320, redemptionMs: 1000 };

/** whisper's input languages the Voz screen offers, with their names. */
export const VOICE_LANGUAGES: readonly [string, string][] = [
  ["auto", "Detectar automáticamente"], ["es", "Español"], ["en", "Inglés"], ["pt", "Portugués"], ["fr", "Francés"], ["de", "Alemán"],
  ["it", "Italiano"], ["zh", "Chino"], ["ja", "Japonés"], ["ko", "Coreano"], ["ar", "Árabe"], ["ru", "Ruso"], ["hi", "Hindi"],
  ["bn", "Bengalí"], ["ta", "Tamil"], ["te", "Telugu"], ["mr", "Marathi"], ["gu", "Guyaratí"], ["kn", "Canarés"], ["ml", "Malayalam"], ["ur", "Urdu"],
];
