import { useState } from "react";
import { useLocalModelSwitch } from "./use-local-model";

/**
 * The admin's switch of the Instance's Local model, in the composer and in Ajustes. Every Session
 * follows it on its next turn. A refusal (turns in course, the daemon busy, a model that did not come
 * up) is shown here.
 */
export function ModelPicker({ onSwitched, compact = false }: { onSwitched?: () => void; compact?: boolean }) {
  const { status, loadError, active, models, switching, error, activate } = useLocalModelSwitch({ onSwitched });
  const [chosen, setChosen] = useState<string>("");
  const value = chosen || active || "";

  if (status === "loading") return <span className="text-xs text-fg-subtle">Cargando modelos…</span>;
  if (loadError) return <span role="alert" className="text-xs text-red-500">{loadError}</span>;

  return (
    <div className={compact ? "flex flex-wrap items-center gap-2" : "space-y-2"}>
      <label className="flex items-center gap-2 text-xs text-fg-muted">
        {compact ? <span className="sr-only">Local model</span> : <span>Local model activo</span>}
        <select
          aria-label="Local model"
          value={value}
          disabled={switching}
          onChange={(e) => setChosen(e.target.value)}
          className="rounded-lg border border-line bg-canvas px-2 py-1 text-xs text-fg"
        >
          {models.map((m) => (
            <option key={m.id} value={m.id} disabled={!m.activable}>
              {m.name ?? m.id}{m.context_window ? ` · ${Math.round(m.context_window / 1000)}k` : ""}{m.activable ? "" : " (no activable)"}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        disabled={switching || !value || value === active}
        onClick={() => void activate(value)}
        className="rounded-lg border border-line px-2 py-1 text-xs text-fg hover:bg-fg/5 disabled:opacity-40"
      >
        {switching ? "Cambiando…" : "Cambiar modelo"}
      </button>
      {error && <p role="alert" className="text-xs text-red-500">{error}</p>}
    </div>
  );
}
