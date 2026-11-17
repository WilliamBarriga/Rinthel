import { useEffect, useState } from "react";
import type { PrefillEvent } from "@deck/contract";

/** What the Agent is busy with before it can speak: reading the prompt, or compacting the conversation. */
export type WorkPhase =
  | { kind: "processing"; prefill: PrefillEvent }
  | { kind: "compacting"; since: number | null };

/** The progress of the work in course, compact under the voice orb. */
export function ActivityProgress({ phase }: { phase: WorkPhase }) {
  const [now, setNow] = useState(Date.now);
  const [shown] = useState(Date.now);
  const compacting = phase.kind === "compacting";
  useEffect(() => {
    if (!compacting) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [compacting]);
  if (phase.kind === "compacting") {
    const seconds = Math.max(0, Math.floor((now - (phase.since ?? shown)) / 1000));
    const elapsed = seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
    return (
      <div className="activity-progress activity-progress-compact">
        <div className="activity-progress-heading"><span role="status">Compactando la conversación</span><span>{elapsed}</span></div>
        <div className="activity-progress-track" role="progressbar" aria-label="Compactación de la conversación" aria-valuemin={0} aria-valuemax={100}>
          <div className="activity-progress-indeterminate" />
        </div>
      </div>
    );
  }
  const { total, processed, cache } = phase.prefill;
  const done = Math.max(0, Math.min(total, processed + cache));
  const percent = total > 0 ? Math.round((done / total) * 100) : undefined;
  return (
    <div className="activity-progress activity-progress-compact">
      <div className="activity-progress-heading"><span role="status">Leyendo el contexto…</span><span>{percent !== undefined ? `${percent}%` : ""}</span></div>
      <div className="activity-progress-track" role="progressbar" aria-label="Procesamiento del prompt" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
        <div className={percent === undefined ? "activity-progress-indeterminate" : ""} style={percent === undefined ? undefined : { width: `${percent}%` }} />
      </div>
    </div>
  );
}
