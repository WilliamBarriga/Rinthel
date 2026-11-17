import { useReportExpired } from "../failure-context";
import { useVoiceSettings } from "./use-voice-settings";
import { VOICE_LANGUAGES } from "./vad";

const DETECTION = [
  ["redemptionMs", "Silencio de fin de turno", 200, 3000, 50, "ms", "Cuánto esperar tras tu voz antes de enviar el turno."],
  ["positiveSpeechThreshold", "Umbral de inicio de voz", 0.01, 1, 0.01, "", "Más alto rechaza más ruido, pero puede perder la voz baja."],
  ["negativeSpeechThreshold", "Umbral de fin de voz", 0, 0.99, 0.01, "", "Por debajo, el audio cuenta como silencio. Debe ser menor que el de inicio."],
  ["minSpeechMs", "Duración mínima de voz", 64, 2000, 16, "ms", "Los sonidos más cortos se ignoran como disparos accidentales."],
  ["preSpeechPadMs", "Audio antes de la voz", 0, 1000, 20, "ms", "Conserva el comienzo de las palabras antes de confirmar la voz."],
] as const;

/** Voz: each user's own voice settings, for talking with the Agent in their Sessions. */
export function VoicePage() {
  const voice = useVoiceSettings({ onFailure: useReportExpired() });
  const { config, instance, vad, update, busy, saved } = voice;
  return (
    <section aria-label="Voz" className="mx-auto w-full max-w-2xl space-y-4 px-5 py-5">
      <h1 className="ui-title text-fg">Voz</h1>
      <p className="text-xs text-fg-subtle">Habla con el Agente en tus Sesiones, con manos libres: interrumpe cuando quieras. La voz va directo a los servicios de voz de la Instance.</p>
      {voice.loadError && <p role="alert" className="text-xs text-red-500">{voice.loadError}</p>}
      {instance && !(instance.stt && instance.tts) && (
        <p role="note" className="rounded-lg border border-line px-3 py-2 text-xs text-fg-muted">
          La Instance no tiene la voz activa ({[!instance.stt && "stt", !instance.tts && "tts"].filter(Boolean).join(" y ")}): un admin puede activarla en Ajustes. Mientras tanto, la voz no aparece en las Sesiones.
        </p>
      )}
      {config && (
        <>
          <label className="flex items-center gap-2 text-sm text-fg">
            <input type="checkbox" checked={config.enabled} onChange={(e) => update({ enabled: e.target.checked })} />
            Mostrar la voz en mis Sesiones
          </label>
          <label className="block text-xs text-fg-muted">
            Idioma de entrada
            <select className="mt-1.5 w-full rounded-lg border border-line bg-canvas px-3 py-2 text-xs" value={config.language || "auto"} onChange={(e) => update({ language: e.target.value })}>
              {VOICE_LANGUAGES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <p className="text-xs text-fg-subtle">Elegir tu idioma mejora el reconocimiento en turnos cortos.</p>
          <details className="rounded-xl border border-line p-4">
            <summary className="cursor-pointer text-sm font-medium text-fg">Detección de voz<span className="mt-1 block text-xs font-normal text-fg-muted">Ritmo de los turnos y sensibilidad del micrófono · Silero VAD</span></summary>
            <div className="mt-4 space-y-4">
              <p className="text-xs text-fg-subtle">Guarda y vuelve a activar la voz para aplicarlo. Un silencio más corto responde antes, pero puede cortar las pausas.</p>
              {DETECTION.map(([key, label, min, max, step, unit, help]) => (
                <label key={key} className="block text-xs text-fg-muted">
                  <span className="flex justify-between gap-3"><span>{label}</span><span className="tabular-nums text-accent">{vad[key]} {unit}</span></span>
                  <input type="range" className="mt-2 w-full accent-current" min={min} max={max} step={step} value={vad[key]} onChange={(e) => update({ vad: { ...vad, [key]: Number(e.target.value) } })} />
                  <span className="mt-1 block text-fg-subtle">{help}</span>
                </label>
              ))}
              <button type="button" className="rounded-lg border border-line px-3 py-1.5 text-xs" onClick={voice.resetVad}>Restablecer la detección</button>
            </div>
          </details>
          <div className="flex justify-end">
            <button type="button" disabled={busy} className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-accent-fg disabled:opacity-40" onClick={() => void voice.save()}>
              {busy ? "Guardando…" : saved ? "Guardado" : "Guardar la voz"}
            </button>
          </div>
          {voice.actionError && <p role="alert" className="text-xs text-red-500">{voice.actionError}</p>}
        </>
      )}
    </section>
  );
}
