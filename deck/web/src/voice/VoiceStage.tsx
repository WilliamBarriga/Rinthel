import { useEffect, useRef, type MutableRefObject } from "react";
import { LuMic, LuMicOff, LuVolume2, LuVolumeX, LuX } from "react-icons/lu";
import { ActivityProgress, type WorkPhase } from "./ActivityProgress";
import { VoiceToolActivity } from "./VoiceToolActivity";
import type { VoicePhase } from "./hands-free";
import type { VoiceLevels } from "./model/voice-session";
import type { VoiceEvent } from "./use-voice-profiling";

type OrbMode = "input" | "output" | "idle" | "muted";

/** The shape follows real RMS audio levels; the slow drift only gives idle depth. */
function VoiceOrb({ mode, levels }: { mode: OrbMode; levels: MutableRefObject<VoiceLevels> }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const current = useRef(mode); current.current = mode;
  useEffect(() => {
    const element = canvas.current!;
    const ctx = element.getContext?.("2d");
    if (!ctx) return;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const size = 600;
    const ratio = Math.min(devicePixelRatio || 1, 2);
    element.width = size * ratio; element.height = size * ratio;
    ctx.scale(ratio, ratio);
    let frame = 0, level = 0;
    let color = [130, 188, 255];
    const colors = { input: [83, 247, 215], output: [190, 159, 255], idle: [130, 188, 255], muted: [161, 179, 204] };
    const render = (timestamp: number) => {
      const mode = current.current;
      const value = mode === "input" ? levels.current.input : mode === "output" ? levels.current.output : 0;
      level += (value - level) * (value > level ? 0.3 : 0.09);
      color = color.map((v, i) => v + (colors[mode][i] - v) * 0.06);
      const rgb = color.map(Math.round).join(",");
      const t = reduced ? 0 : timestamp * 0.00055;
      const r = 132 + level * (reduced ? 5 : 28);
      ctx.clearRect(0, 0, size, size);
      ctx.save(); ctx.translate(size / 2, size / 2);
      const halo = ctx.createRadialGradient(0, 0, r * 0.65, 0, 0, r * 1.7);
      halo.addColorStop(0, `rgba(${rgb},${0.3 + level * 0.18})`); halo.addColorStop(1, `rgba(${rgb},0)`);
      ctx.fillStyle = halo; ctx.fillRect(-size / 2, -size / 2, size, size);
      for (let ring = 0; ring < 2; ring++) {
        ctx.beginPath();
        ctx.ellipse(0, 0, r + 20 + ring * 16 + level * 7, r + 18 + ring * 16, Math.sin(t) * 0.12, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(${rgb},${0.2 + level * 0.15 - ring * 0.05})`; ctx.lineWidth = 1.2; ctx.stroke();
      }
      ctx.beginPath();
      for (let i = 0; i <= 160; i++) {
        const a = (i / 160) * Math.PI * 2;
        const wave = Math.sin(a * 3 + t * 1.3) * (3 + level * 7) + Math.sin(a * 5 - t * 2) * level * 10;
        const x = Math.cos(a) * (r + wave), y = Math.sin(a) * (r + wave);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath();
      const sphere = ctx.createRadialGradient(-r * 0.32, -r * 0.45, 1, r * 0.12, r * 0.1, r * 1.32);
      sphere.addColorStop(0, `rgba(${rgb},0.98)`); sphere.addColorStop(0.32, `rgba(${rgb},0.95)`);
      sphere.addColorStop(0.7, `rgb(${color.map((v) => Math.round(v * 0.62)).join(",")})`); sphere.addColorStop(1, `rgb(${color.map((v) => Math.round(v * 0.34)).join(",")})`);
      ctx.shadowColor = `rgba(${rgb},0.65)`; ctx.shadowBlur = 22;
      ctx.fillStyle = sphere; ctx.fill(); ctx.shadowBlur = 0;
      ctx.strokeStyle = `rgba(${rgb},0.8)`; ctx.lineWidth = 1.8; ctx.stroke(); ctx.save(); ctx.clip();
      // Translucent ribbons bend across the sphere rather than flat sine bars.
      for (let band = 0; band < 15; band++) {
        const y = -r + band * r * 0.15;
        const bend = Math.sin(t + band * 0.27) * 35 + level * 22;
        ctx.beginPath(); ctx.moveTo(-r * 1.3, y);
        ctx.bezierCurveTo(-r * 0.45, y - 60 + bend, r * 0.35, y + 65 + bend, r * 1.3, y - 20);
        ctx.bezierCurveTo(r * 0.3, y + 85 + bend, -r * 0.4, y - 40 + bend, -r * 1.3, y + 9);
        const ribbon = ctx.createLinearGradient(-r, -r, r, r);
        ribbon.addColorStop(0, `rgba(231,255,255,${0.04 + band * 0.003})`);
        ribbon.addColorStop(0.45, `rgba(${rgb},${0.24 + level * 0.12})`);
        ribbon.addColorStop(1, "rgba(192,190,255,0.03)");
        ctx.fillStyle = ribbon; ctx.fill();
      }
      const shine = ctx.createRadialGradient(-r * 0.33, -r * 0.55, 0, -r * 0.33, -r * 0.55, r * 0.85);
      shine.addColorStop(0, "rgba(238,255,255,0.45)"); shine.addColorStop(0.35, "rgba(233,253,255,0.08)"); shine.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = shine; ctx.fillRect(-r, -r, 2 * r, 2 * r);
      ctx.restore(); ctx.restore();
      frame = requestAnimationFrame(render);
    };
    frame = requestAnimationFrame(render);
    return () => cancelAnimationFrame(frame);
  }, [levels]);
  return <canvas ref={canvas} aria-hidden="true" className="voice-orb" data-mode={mode} />;
}

export interface VoiceStageProps {
  title: string;
  /** What the Agent is busy with before it can speak, shown under the orb. */
  workPhase: WorkPhase | null;
  phase: VoicePhase; starting: boolean; muted: boolean; speaking: boolean;
  levels: MutableRefObject<VoiceLevels>; transcript: string; error: string;
  events: VoiceEvent[];
  sounds: boolean; onSounds: () => void; onMute: () => void; onEnd: () => void;
}

/** Voice mode: the orb, what voice is doing, the live transcription and its controls, in place of the transcript and composer. */
export function VoiceStage({ title, workPhase, phase, starting, muted, speaking, levels, transcript, error, events, sounds, onSounds, onMute, onEnd }: VoiceStageProps) {
  const end = useRef<HTMLButtonElement>(null);
  useEffect(() => { end.current?.focus({ preventScroll: true }); }, []);
  const input = !muted && phase === "Te escucho";
  const mode: OrbMode = input ? "input" : speaking ? "output" : muted ? "muted" : "idle";
  const status = starting ? "Conectando" : input ? "Te escucho" : speaking ? "Hablando" : phase === "Hablando" ? "Preparando la respuesta"
    : phase === "Pensando" ? "Pensando" : phase === "Transcribiendo" ? "Transcribiendo" : phase === "Compactando el contexto" ? phase : muted ? "Micrófono silenciado" : "Escuchando";
  return (
    <section className="voice-stage" aria-label="Conversación por voz" data-mode={mode}>
      <header className="voice-stage-header">
        <span className="voice-stage-session">{title}</span>
        <div className="voice-utilities">
          <button type="button" onClick={onSounds} title={sounds ? "Silenciar efectos de sonido" : "Activar efectos de sonido"} aria-label={sounds ? "Silenciar efectos de sonido" : "Activar efectos de sonido"} aria-pressed={sounds}>{sounds ? <LuVolume2 /> : <LuVolumeX />}</button>
        </div>
      </header>
      <VoiceToolActivity events={events} />
      <div className="voice-presence">
        <div className="voice-avatar"><VoiceOrb mode={mode} levels={levels} /></div>
        <div className="voice-dock-center">
          {workPhase ? <ActivityProgress phase={workPhase} /> : <div className="voice-status" role="status"><span />{status}</div>}
        </div>
        {transcript && (input || phase === "Transcribiendo") && <p className="voice-live-transcript" aria-label="Transcripción en vivo">{transcript}</p>}
        <div className="voice-stage-controls">
          <button type="button" className={`voice-stage-action ${muted ? "is-muted" : ""}`} title={muted ? "Activar micrófono" : "Silenciar micrófono"} aria-label={muted ? "Activar micrófono" : "Silenciar micrófono"} aria-pressed={muted} disabled={starting} onClick={onMute}>
            <LuMicOff className={muted ? "" : "hidden"} /><LuMic className={muted ? "hidden" : ""} />
          </button>
          <button ref={end} type="button" className="voice-stage-action voice-end" title="Terminar modo voz" aria-label="Terminar modo voz" onClick={onEnd}><LuX /></button>
        </div>
      </div>
      {error && <p role="alert" className="voice-stage-error">{error}</p>}
    </section>
  );
}
