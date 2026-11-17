import { useState } from "react";
import type { ModelEntry } from "@deck/contract";
import { useVoiceModels } from "./use-local-model";

const CAPABILITIES = [
  ["stt", "Reconocimiento de voz (stt)"],
  ["tts", "Síntesis de voz (tts)"],
] as const;

/**
 * The admin's switch of the Instance's voice, in Ajustes: per Capability, which catalog entry is on, or
 * off. Turning one on starts its voice service on the host; off stops it. Voice runs on Linux only.
 */
export function VoiceModels() {
  const voice = useVoiceModels();
  if (voice.status === "loading") return <span className="text-xs text-fg-subtle">Cargando la voz…</span>;
  if (voice.loadError) return <span role="alert" className="text-xs text-red-500">{voice.loadError}</span>;
  return (
    <div className="space-y-3">
      {CAPABILITIES.map(([name, label]) => (
        <VoiceCapabilityRow
          key={name}
          label={label}
          models={voice[name].models}
          active={voice[name].active}
          busy={voice.busy}
          onActivate={(id) => void voice.activate(id)}
          onOff={() => void voice.off(name)}
        />
      ))}
      {voice.error && <p role="alert" className="text-xs text-red-500">{voice.error}</p>}
    </div>
  );
}

function VoiceCapabilityRow({ label, models, active, busy, onActivate, onOff }: {
  label: string;
  models: ModelEntry[];
  active: string | null;
  busy: boolean;
  onActivate: (id: string) => void;
  onOff: () => void;
}) {
  const [chosen, setChosen] = useState("");
  const value = chosen || active || models.find((m) => m.activable)?.id || "";
  return (
    <fieldset aria-label={label} className="flex flex-wrap items-center gap-2 rounded-lg border border-line px-3 py-2">
      <legend className="px-1 text-xs text-fg-muted">{label}</legend>
      <span className="text-xs text-fg">{active ? `Activo: ${active}` : "Apagado"}</span>
      {models.length === 0 ? (
        <span className="text-xs text-fg-subtle">El catálogo no tiene modelos de esta Capability.</span>
      ) : (
        <>
          <select
            aria-label={`Modelo de ${label}`}
            value={value}
            disabled={busy}
            onChange={(e) => setChosen(e.target.value)}
            className="rounded-lg border border-line bg-canvas px-2 py-1 text-xs text-fg"
          >
            {models.map((m) => (
              <option key={m.id} value={m.id} disabled={!m.activable}>
                {m.name ?? m.id}{m.activable ? "" : " (no activable)"}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={busy || !value || value === active}
            onClick={() => onActivate(value)}
            className="rounded-lg border border-line px-2 py-1 text-xs text-fg hover:bg-fg/5 disabled:opacity-40"
          >
            Activar
          </button>
        </>
      )}
      <button
        type="button"
        disabled={busy || !active}
        onClick={onOff}
        className="rounded-lg border border-line px-2 py-1 text-xs text-fg hover:bg-fg/5 disabled:opacity-40"
      >
        Apagar
      </button>
    </fieldset>
  );
}
