import { useCallback, useRef, useState } from "react";
import { api } from "./api";

export type RecorderState = "idle" | "recording" | "transcribing";

/**
 * Mic capture as a single toggle — not push-to-talk. Records into one Blob,
 * then hands it to whisper.cpp via the portal proxy.
 */
export function useVoiceRecorder() {
  const [state, setState] = useState<RecorderState>("idle");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  };

  const start = useCallback(async () => {
    if (recorderRef.current) return;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;
    chunksRef.current = [];
    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorderRef.current = recorder;
    recorder.start();
    setState("recording");
  }, []);

  const stop = useCallback((): Promise<{ text: string; lang: "es" | "en" } | null> => {
    const recorder = recorderRef.current;
    if (!recorder) return Promise.resolve(null);
    return new Promise((resolve) => {
      recorder.onstop = async () => {
        stopStream();
        recorderRef.current = null;
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        chunksRef.current = [];
        setState("transcribing");
        try {
          resolve(await api.transcribeVoice(blob));
        } catch {
          resolve(null);
        } finally {
          setState("idle");
        }
      };
      recorder.stop();
    });
  }, []);

  /** What the mic button calls — starts on the first click, transcribes on the second. */
  const toggle = useCallback(async (): Promise<{ text: string; lang: "es" | "en" } | null> => {
    if (state === "recording") return stop();
    if (state === "idle") {
      await start();
      return null;
    }
    return null;
  }, [state, start, stop]);

  return { state, toggle };
}
