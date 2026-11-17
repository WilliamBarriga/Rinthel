import { createPortal } from "react-dom";
import { LuGauge, LuLoaderCircle, LuMic } from "react-icons/lu";
import { VoiceProfile } from "./VoiceProfile";
import { VoiceStage } from "./VoiceStage";
import type { WorkPhase } from "./ActivityProgress";
import { useVoiceController, type VoiceControllerOptions } from "./use-voice-controller";

export interface VoiceControlProps extends VoiceControllerOptions {
  title: string;
  /** Where the stage goes while voice mode is on: the chat hands its body over. */
  stageTarget: HTMLElement | null;
  workPhase: WorkPhase | null;
}

/**
 * The composer's microphone: it turns hands-free voice on, and while on the stage takes the chat's
 * place. Nothing shows unless the reader turned voice on and the Instance has `stt` and `tts`.
 */
export function VoiceControl(props: VoiceControlProps) {
  const model = useVoiceController(props);
  return <VoiceControlView {...props} model={model} />;
}

export function VoiceControlView({ model, title, stageTarget, workPhase, events }: VoiceControlProps & { model: ReturnType<typeof useVoiceController> }) {
  const { available, enabled, starting, phase, error, muted, transcript, speaking, sounds, toggleSounds, levels, toggleMute, endMode, start, startButton, profileOpen, profiler, comparison, sequentialMode, sentenceMode, prefetchMode, toggleProfile, closeProfile } = model;
  if (!available) return null;
  const mode = sequentialMode ? ` · ${sentenceMode ? (prefetchMode ? "frases con audio en búfer y adelanto" : "frases con audio en búfer") : "secuencial"}` : comparison ? " · en flujo" : "";
  return (
    <>
      {profileOpen && createPortal(<VoiceProfile profiler={profiler.current!} onClose={closeProfile} />, document.body)}
      {(starting || enabled) && stageTarget && createPortal(
        <VoiceStage title={`${title}${mode}`} workPhase={workPhase} phase={phase} starting={starting} muted={muted} speaking={speaking}
          levels={levels} transcript={transcript} error={error} events={events} sounds={sounds} onSounds={toggleSounds} onMute={() => void toggleMute()} onEnd={endMode} />,
        stageTarget,
      )}
      <div className="relative flex items-center gap-1">
        <button type="button" className="prompt-action" aria-label="Perfil de latencia de voz" title="Perfil de latencia de voz" aria-pressed={profileOpen} onClick={toggleProfile}><LuGauge /></button>
        {error && !enabled && !starting && <p role="alert" className="absolute bottom-full right-0 mb-3 w-64 rounded-xl border border-line bg-surface p-3 text-xs text-danger shadow-pop">{error}</p>}
        <button ref={startButton} type="button" onClick={() => void start()} aria-label="Activar voz manos libres" title="Conversar por voz" className="prompt-action">
          {starting ? <LuLoaderCircle aria-hidden className="animate-spin" /> : <LuMic aria-hidden />}
        </button>
      </div>
    </>
  );
}
