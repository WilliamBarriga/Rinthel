import { voiceProfileSummary, type VoiceProfiler } from "./voice-profile";

const STAGES: Record<string, string> = {
  "Turn detection": "Detección del turno",
  "Remaining transcription": "Transcripción restante",
  "Dispatch / pending abort": "Envío / interrupción pendiente",
  "Request setup / prefill → first token": "Preparación / lectura del prompt → primer token",
  "Thinking / tools → first reply text": "Razonamiento / herramientas → primer texto",
  "Sentence accumulation": "Acumulación de la frase",
  "TTS queue": "Cola del TTS",
  "TTS request → first audio bytes": "Petición al TTS → primeros bytes de audio",
  "Audio buffering / decoding": "Búfer / decodificación del audio",
  "Playback queue / output estimate": "Cola de reproducción / salida estimada",
};

/** Where the time of the last voice turn went, from the last detected speech to the reply's audio. */
export function VoiceProfile({ profiler, onClose }: { profiler: VoiceProfiler; onClose: () => void }) {
  const trace = profiler.traces.at(-1), summary = trace && voiceProfileSummary(trace);
  const download = () => {
    const data = profiler.traces.map((t) => ({ ...t, summary: voiceProfileSummary(t) }));
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = document.createElement("a"); a.href = url; a.download = "voice-latency.json"; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <aside className="voice-profile" aria-label="Latencia de voz">
      <header><strong>Latencia de voz</strong><button type="button" onClick={onClose} aria-label="Cerrar perfil de voz">×</button></header>
      <p>{trace ? `Turno ${trace.id} · ${trace.status}` : "Habla un turno para empezar a medir."}</p>
      {summary ? (
        <>
          <strong>{(summary.totalMs / 1000).toFixed(2)} s desde la última voz detectada hasta el audio de la respuesta</strong>
          <table><tbody>{summary.stages.map((s) => <tr key={s.label}><td>{STAGES[s.label] ?? s.label}</td><td>{Math.round(s.ms)} ms</td><td>{s.percent.toFixed(1)}%</td></tr>)}</tbody></table>
        </>
      ) : <p>Esperando a que suene la primera respuesta…</p>}
      <p>La salida es una estimación del AudioContext, no una medida del micrófono. Las frases de relleno no cuentan. Las etapas son tiempo de reloj, no tiempo de GPU.</p>
      <details><summary>Eventos de tiempo ({trace?.marks.length ?? 0})</summary><pre>{trace?.marks.map((m) => `${Math.round(m.at - trace.started)}ms ${m.name} ${m.detail ? JSON.stringify(m.detail) : ""}`).join("\n")}</pre></details>
      <button type="button" disabled={!profiler.traces.length} onClick={download}>Descargar informe de tiempos</button>
    </aside>
  );
}
