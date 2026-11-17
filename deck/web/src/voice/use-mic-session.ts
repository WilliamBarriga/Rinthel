import { useEffect, useRef, type Dispatch, type MutableRefObject } from "react";
import type { MicVAD } from "@ricky0123/vad-web";
import { voiceCue } from "./voice-cues";
import type { TranscriptItem as Item } from "../chat/model/transcript";
import { LiveTranscription } from "./live-transcription";
import { samplesWav } from "./speech-text";
import { HandsFreeVoice } from "./hands-free";
import { useVoiceSpeech } from "../ports/context";
import type { PreparedSpeech } from "./speech-pipeline";
import type { VoiceLevels, VoiceSessionEvent, VoiceSessionReading } from "./model/voice-session";
import type { VoiceSettings } from "./use-voice-config";
import type { useVoiceProfiling } from "./use-voice-profiling";
import type { useVoiceSounds } from "./use-voice-sounds";

/** What the microphone session reads from the latest render; it outlives any one render. */
export interface MicSessionInput {
  items: Item[]; running: boolean; compacting: boolean;
  onSend(text: string, options?: { voice?: boolean }): Promise<void>;
  onAbort(): Promise<void>;
}
export interface MicSessionOptions {
  sessionId: string;
  starting: boolean;
  settings: MutableRefObject<VoiceSettings>;
  input: MutableRefObject<MicSessionInput>;
  dispatch: Dispatch<VoiceSessionEvent>;
  levels: MutableRefObject<VoiceLevels>;
  profile: ReturnType<typeof useVoiceProfiling>;
  sounds: ReturnType<typeof useVoiceSounds>;
  synthesize(text: string, signal: AbortSignal, audio: AudioContext, kind?: "reply" | "status"): Promise<PreparedSpeech>;
}

/**
 * Everything that holds the microphone: the stream, the audio contexts, the voice-activity detector,
 * the live transcription and the hands-free engine. `stop` releases all of them and is safe at any
 * point of `start`, including while the browser is still asking for permission.
 *
 * Refs here are not copies of reducer state. `epoch`, `startingNow`, `muteBusy` and `mutedRef` answer
 * questions that callbacks created inside `start` (detector, timers, track events) ask long after the
 * render that made them, and a double click can arrive before the first dispatch renders: a closure
 * over `state` would be stale, and mute must take effect before its first `await`.
 */
export function useMicSession({ sessionId, starting, settings, input, dispatch, levels, profile, sounds, synthesize }: MicSessionOptions) {
  const speech = useVoiceSpeech();
  const { profiling, profiler, profileSeq, eventSeq, profileMark } = profile;
  const { soundContext, soundsEnabled, cue } = sounds;
  const transcription = useRef<LiveTranscription | null>(null);
  const voice = useRef<HandsFreeVoice | null>(null);
  const vad = useRef<MicVAD | null>(null);
  const context = useRef<AudioContext | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const maxTurn = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  /** Bumped by every stop and start: a late `await` compares it to know it was cancelled. */
  const epoch = useRef(0);
  const startingNow = useRef(false);
  const mounted = useRef(false);
  const mutedRef = useRef(false);
  const muteBusy = useRef(false);

  const stop = () => {
    profiler.current?.close("stopped");
    epoch.current++;
    startingNow.current = false;
    const sound = soundContext.current; soundContext.current = null;
    if (sound) { if (soundsEnabled.current && mounted.current) voiceCue(sound, "end"); setTimeout(() => { if (sound.state !== "closed") void sound.close(); }, 180); }
    mutedRef.current = false;
    levels.current = { input: 0, output: 0 };
    clearTimeout(maxTurn.current);
    voice.current?.stop(); voice.current = null;
    transcription.current?.reset(); transcription.current = null;
    const detector = vad.current; vad.current = null;
    void detector?.destroy().catch(() => {});
    stream.current?.getTracks().forEach(track => track.stop()); stream.current = null;
    const audio = context.current; context.current = null;
    if (audio && audio.state !== "closed") void audio.close();
    if (mounted.current) dispatch({ type: "stop" });
  };
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; stop(); };
  }, []);

  const toggleMute = async () => {
    const detector = vad.current;
    if (!detector || muteBusy.current) return;
    const version = epoch.current;
    const next = !mutedRef.current;
    muteBusy.current = true;
    mutedRef.current = next;
    dispatch({ type: "read", reading: { muted: next } }); cue(next ? "mute" : "unmute");
    clearTimeout(maxTurn.current);
    levels.current.input = 0;
    voice.current?.setMuted(next);
    if (next) { transcription.current?.reset(); profiler.current?.close("muted"); }
    try {
      if (next) {
        stream.current?.getTracks().forEach(track => { track.enabled = false; });
        detector.setOptions({ submitUserSpeechOnPause: false });
        await detector.pause();
      } else {
        detector.setOptions({ submitUserSpeechOnPause: true });
        stream.current?.getTracks().forEach(track => { track.enabled = true; });
        await detector.start();
      }
    } catch (e) {
      if (epoch.current === version) { dispatch({ type: "error", value: (e as Error).message }); stop(); }
    } finally { muteBusy.current = false; }
  };

  const start = async () => {
    if (voice.current || starting || startingNow.current) { stop(); return; }
    startingNow.current = true;
    const version = ++epoch.current;
    const current = () => mounted.current && epoch.current === version;
    const fail = (message: string) => { dispatch({ type: "error", value: message }); stop(); };
    const read = (reading: VoiceSessionReading) => dispatch({ type: "read", reading });
    dispatch({ type: "start" }); mutedRef.current = false;
    try {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia)
        throw new Error("El micrófono necesita HTTPS o localhost.");
      const sound = new AudioContext(); soundContext.current = sound;
      await sound.resume();
      if (!current()) return;
      const audio = new AudioContext(); context.current = audio;
      await audio.resume();
      if (!current()) return;
      const mic = await navigator.mediaDevices.getUserMedia({ audio: {
        channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      } });
      if (!current()) { mic.getTracks().forEach(track => track.stop()); return; }
      stream.current = mic;
      const detectorModule = await import("@ricky0123/vad-web");
      if (!current()) return;
      const chosen = settings.current;
      const live = new LiveTranscription(async (samples, signal) => {
        const trace = profiling.current ? profiler.current!.current : undefined;
        const started = performance.now(); if (trace) profiler.current!.mark("stt_request", { audioMs: samples.length / 16 }, trace);
        try {
          const result = await speech.transcribe(sessionId, samplesWav(samples), signal);
          if (trace) profiler.current!.mark("stt_result", { requestMs: performance.now() - started, serverTiming: result.serverTiming, ok: true }, trace);
          return result.text;
        } catch (e) {
          if (trace) profiler.current!.mark("stt_result", { requestMs: performance.now() - started, serverTiming: "", ok: false }, trace);
          throw e;
        }
      }, text => { if (current()) read({ transcript: text }); }, !chosen.sequential);
      transcription.current = live;
      const controller = new HandsFreeVoice({
        statusSpeech: chosen.statusSpeech,
        sequential: chosen.sequential,
        sentenceChunks: chosen.sentenceChunks,
        ttsPrefetch: chosen.ttsPrefetch,
        transcribe: async (samples, signal) => { const result = await live.finish(samples, signal); profileMark("transcript_ready"); return result; },
        send: text => { profileSeq.current = eventSeq.current; profileMark("send"); cue("sent"); return input.current.onSend(text, { voice: true }); },
        abort: () => input.current.onAbort(),
        agentRunning: () => input.current.running,
        synthesize: (text, signal, kind) => synthesize(text, signal, audio, kind),
        trace: profileMark,
        phase: value => { if (current()) read({ phase: value }); },
        error: message => { if (current()) { dispatch({ type: "error", value: message }); profiler.current?.close("error"); } },
      }, input.current.items);
      voice.current = controller;
      controller.setCompacting(input.current.compacting);
      const detector = await detectorModule.MicVAD.new({
        model: "v5", audioContext: audio, startOnLoad: false,
        baseAssetPath: "/voice-assets/", onnxWASMBasePath: "/voice-assets/",
        ortConfig: ort => { ort.env.wasm.numThreads = 1; },
        getStream: async () => mic,
        pauseStream: async () => {},
        resumeStream: async () => mic,
        ...chosen.vad,
        submitUserSpeechOnPause: true,
        onSpeechStart: () => { if (current() && !mutedRef.current && !input.current.compacting) { if (profiling.current) profiler.current!.begin(); live.begin(); } },
        onVADMisfire: () => { if (current()) { live.discard(); if (profiling.current) profiler.current!.close("vad_misfire"); } },
        onFrameProcessed: (probabilities, frame) => {
          if (current() && !mutedRef.current && profiling.current && probabilities.isSpeech >= 0.35) profiler.current!.lastSpeech();
          if (current() && !mutedRef.current && !input.current.compacting) live.frame(probabilities.isSpeech, frame);
          if (current() && !mutedRef.current) levels.current.input = Math.min(1, Math.sqrt(frame.reduce((sum, value) => sum + value * value, 0) / frame.length) * 7);
        },
        onSpeechRealStart: () => {
          if (!current() || mutedRef.current) return;
          read({ error: "" }); if (input.current.compacting) live.discard(); else live.confirm(); controller.speechStart();
          clearTimeout(maxTurn.current);
          maxTurn.current = setTimeout(async () => {
            if (!current() || !vad.current) return;
            // Bound recording size; keep the same mic stream while submitting
            // the segment and automatically listening for the continuation.
            const active = vad.current;
            try { await active.pause(); if (current()) await active.start(); }
            catch (e) { if (current()) fail((e as Error).message); }
          }, 60000);
        },
        onSpeechEnd: samples => {
          clearTimeout(maxTurn.current);
          if (current() && !mutedRef.current) { if (!input.current.compacting) { profileMark("endpoint"); live.end(samples); } controller.speechEnd(samples); }
        },
      });
      if (!current()) { await detector.destroy(); return; }
      vad.current = detector;
      for (const track of mic.getTracks()) track.onended = () => {
        if (current()) fail("El micrófono se desconectó. Vuelve a conectarlo y activa la voz otra vez.");
      };
      await detector.start();
      if (!current()) return;
      startingNow.current = false;
      dispatch({ type: "started" }); cue("start");
    } catch (e) {
      if (current()) fail((e as Error).message);
    }
  };

  return { start, stop, toggleMute, engine: voice, transcription };
}
