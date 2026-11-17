import { useRef, type MutableRefObject } from "react";
import { useVoiceSpeech } from "../ports/context";
import { preparePcmSpeech, readPcmStream, playAudioBuffer } from "./pcm-stream";
import type { PreparedSpeech } from "./speech-pipeline";
import type { VoiceLevels } from "./model/voice-session";
import type { VoiceProfiler } from "./voice-profile";

export interface VoicePlaybackOptions {
  sessionId: string;
  /** Sequential pipeline: the whole reply is read before it plays. Read per reply, so a saved change applies at once. */
  sequential: () => boolean;
  levels: MutableRefObject<VoiceLevels>;
  profiling: MutableRefObject<boolean>;
  profiler: MutableRefObject<VoiceProfiler | undefined>;
  onSpeaking(speaking: boolean): void;
}

/** Turns a phrase into audio the session's AudioContext can play, measuring the output level. */
export function useVoicePlayback({ sessionId, sequential, levels, profiling, profiler, onSpeaking }: VoicePlaybackOptions) {
  const speech = useVoiceSpeech();
  const latest = useRef({ sequential, onSpeaking }); latest.current = { sequential, onSpeaking };
  return async (text: string, signal: AbortSignal, audio: AudioContext, kind: "reply" | "status" = "reply"): Promise<PreparedSpeech> => {
    const trace = profiling.current ? profiler.current!.current : undefined;
    const mark = (name: string, detail?: Record<string, number | string | boolean>, at?: number) => { if (trace) profiler.current!.mark(kind + "_" + name, detail, trace, at); };
    mark("tts_request");
    // A busy TTS is waited for on the server, so a failure here is final.
    signal.throwIfAborted();
    const reply = await speech.speak(sessionId, text, signal);
    mark("tts_headers", { serverTiming: reply.serverTiming });
    let body = reply.body;
    if (body && trace) {
      let first = true;
      body = body.pipeThrough(new TransformStream<Uint8Array<ArrayBuffer>, Uint8Array<ArrayBuffer>>({ transform(chunk, controller) { if (first && chunk.length) { first = false; mark("first_bytes"); } controller.enqueue(chunk); } }));
    }
    let buffer: AudioBuffer | undefined;
    let stream: Awaited<ReturnType<typeof preparePcmSpeech>> | undefined;
    if (reply.format === "pcm") {
      if (!body) throw new Error("Unsupported speech stream");
      if (!latest.current.sequential() && reply.streaming) stream = await preparePcmSpeech(body, audio, signal);
      else buffer = await readPcmStream(body, audio, signal);
    } else {
      const bytes = await new Response(body).arrayBuffer(); signal.throwIfAborted();
      buffer = await audio.decodeAudioData(bytes); signal.throwIfAborted();
    }
    mark("audio_ready");
    const play = async (playbackSignal: AbortSignal) => {
      playbackSignal.throwIfAborted();
      const analyser = audio.createAnalyser(); analyser.fftSize = 256;
      analyser.connect(audio.destination);
      const samples = new Float32Array(analyser.fftSize);
      let animation = 0;
      const meter = () => {
        analyser.getFloatTimeDomainData(samples);
        levels.current.output = Math.min(1, Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length) * 5);
        animation = requestAnimationFrame(meter);
      };
      try {
        const started = (scheduledAt = audio.currentTime) => {
          mark("playback_scheduled");
          const outputMs = (audio.baseLatency + (audio.outputLatency || 0)) * 1000;
          mark("playback_estimate", { outputLatencyMs: outputMs }, performance.now() + Math.max(0, scheduledAt - audio.currentTime) * 1000 + outputMs);
          latest.current.onSpeaking(true); meter();
        };
        if (stream) await stream.play(analyser, started);
        else await playAudioBuffer(buffer!, audio, analyser, playbackSignal, started);
      } finally {
        analyser.disconnect(); cancelAnimationFrame(animation); levels.current.output = 0;
        latest.current.onSpeaking(false);
      }
    };
    return Object.assign(play, { completed: stream?.completed });
  };
}
