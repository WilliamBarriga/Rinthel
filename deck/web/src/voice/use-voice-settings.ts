import { useCallback, useEffect, useRef, useState } from "react";
import type { VoiceConfig } from "@deck/contract";
import { useVoiceSpeech } from "../ports/context";
import { messageOf } from "../ports/http-errors";
import { DEFAULT_VAD } from "./vad";
import { VOICE_SETTINGS_CHANGED } from "./use-voice-config";

/**
 * Controller of the Voz screen: the reader's own voice settings (whether the controls show in their
 * Sessions, the input language, the speech detection) and whether the Instance has `stt` and `tts`
 * active. `config` is the draft; `update` edits it, `resetVad` puts the detection back to its
 * defaults, `save` writes it and takes the server's answer as the new draft. A refusal leaves
 * `actionError` (a value out of range is the server's to say) and keeps the draft. Nothing throws
 * into a view.
 */
export function useVoiceSettings({ onFailure }: { onFailure?: (error: unknown) => void } = {}) {
  const api = useVoiceSpeech();
  const [config, setConfig] = useState<Required<VoiceConfig> | null>(null);
  const [instance, setInstance] = useState<{ stt: boolean; tts: boolean } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const failure = useRef(onFailure); failure.current = onFailure;
  const live = useRef(true);

  useEffect(() => {
    live.current = true;
    api.settings().then((s) => {
      if (!live.current) return;
      setConfig({ enabled: s.enabled, language: s.language, vad: s.vad });
      setInstance({ stt: s.stt, tts: s.tts });
    }, (e) => {
      failure.current?.(e);
      if (live.current) setLoadError(messageOf(e));
    });
    return () => { live.current = false; };
  }, [api]);

  const update = useCallback((patch: Partial<VoiceConfig>) => {
    setConfig((c) => (c ? { ...c, ...patch } as Required<VoiceConfig> : c));
    setSaved(false);
  }, []);

  const save = useCallback(async (): Promise<boolean> => {
    if (!config) return false;
    setBusy(true);
    setActionError(null);
    try {
      const next = await api.saveConfig(config);
      if (!live.current) return true;
      setConfig(next);
      setSaved(true);
      window.dispatchEvent(new Event(VOICE_SETTINGS_CHANGED));
      return true;
    } catch (e) {
      failure.current?.(e);
      if (live.current) setActionError(messageOf(e));
      return false;
    } finally {
      if (live.current) setBusy(false);
    }
  }, [api, config]);

  return {
    config, instance, loadError, actionError, busy, saved,
    /** The detection value in force: the draft's, or the default for one never saved. */
    vad: { ...DEFAULT_VAD, ...config?.vad },
    update,
    resetVad: () => update({ vad: { ...DEFAULT_VAD } }),
    save,
  };
}
