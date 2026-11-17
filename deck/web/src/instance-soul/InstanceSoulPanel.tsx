import { LuCheck } from "react-icons/lu";
import { useReportFailure } from "../failure-context";
import { useInstanceSoul } from "./use-instance-soul";

/**
 * The Instance SOUL: the `SOUL.md` that tells the Agente who it is in every member's Sesión. A member
 * reads it, read-only; the admin edits it (their own SOUL.md, for their own Sesiones, does not change).
 */
export function InstanceSoulPanel() {
  const soul = useInstanceSoul({ onFailure: useReportFailure() });
  return (
    <section aria-label="SOUL de la Instance" className="space-y-3 px-5 py-5">
      <header>
        <p className="ui-eyebrow">Agente</p>
        <h1 className="ui-title">SOUL de la Instance</h1>
        <p className="ui-description">
          Quién es el Agente para todos los miembros: sus Sesiones la cargan al empezar.
          {soul.status === "ready" && (soul.editable ? " Tu SOUL.md propio no cambia." : " La edita el administrador.")}
        </p>
      </header>
      {soul.status === "error" ? (
        <p role="alert" className="text-sm text-red-500">{soul.error}</p>
      ) : soul.status === "loading" ? (
        <p className="text-sm text-fg-subtle">Cargando…</p>
      ) : (
        <div className="space-y-2">
          {!soul.soul?.exists && <p className="text-sm text-fg-muted">Todavía no está definida: las Sesiones de los miembros no cargan ninguna.</p>}
          <textarea
            value={soul.content}
            onChange={(e) => soul.setContent(e.target.value)}
            readOnly={!soul.editable}
            rows={18}
            aria-label="Contenido de la SOUL de la Instance"
            className="w-full resize-y rounded-lg border border-line bg-canvas px-3 py-2 font-mono text-xs text-fg"
          />
          {soul.editable && (
            <div className="flex items-center gap-2">
              <button type="button" disabled={soul.busy} onClick={() => void soul.save()} className="flex min-h-9 items-center gap-1 rounded-lg border border-line px-3 py-1 text-sm text-fg hover:bg-fg/5 disabled:opacity-40">
                {soul.saved ? <><LuCheck className="h-4 w-4" /> Guardada</> : "Guardar"}
              </button>
            </div>
          )}
          {soul.actionError && <p role="alert" className="text-sm text-red-500">{soul.actionError}</p>}
        </div>
      )}
    </section>
  );
}
