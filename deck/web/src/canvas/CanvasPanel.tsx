import { useEffect, useRef } from "react";
import { LuDownload, LuFileText, LuX } from "react-icons/lu";
import { CanvasBody } from "./canvas-body";
import { useCanvasActions } from "./use-canvas-actions";
import { useSessionCanvases, type SavedFile } from "./use-session-canvases";

/**
 * The Canvases of a Sesión, read only: the Agente writes them and the person reads, follows and
 * downloads the `.md` (or the `.json` of a `ui` one). The view only paints; the list, the stream and
 * the following live in `useSessionCanvases`, what a Canvas looks like by `kind` in `CanvasBody`, and
 * what a click on its interface asks of the server in `useCanvasActions`.
 */
export function CanvasPanel({ sessionId, open, setOpen, saveFile }: { sessionId: string; open: boolean; setOpen: (open: boolean) => void; saveFile?: (file: SavedFile) => void }) {
  const { canvases, selected: canvas, select, error, download } = useSessionCanvases(sessionId, { setOpen, saveFile });
  const { effects, notice, dismiss } = useCanvasActions(sessionId, canvas?.id);
  const viewport = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  useEffect(() => {
    if (canvas?.active_call && follow.current && viewport.current) viewport.current.scrollTop = viewport.current.scrollHeight;
  }, [canvas?.content, canvas?.active_call, open]);
  return (
    <div className={`session-canvases ${open ? "is-open" : ""}`}>
      <button type="button" className="canvas-toggle" onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Canvas de la Sesión" title="Canvas de la Sesión">
        <LuFileText />{canvases.length > 0 && <span>{canvases.length}</span>}
      </button>
      {open && (
        <section className="canvas-panel" aria-label="Espacio de Canvas de la Sesión">
          <header>
            <div><LuFileText /><strong>Canvas de la Sesión</strong></div>
            <div className="canvas-frame-actions">
              <button type="button" aria-label="Descargar Canvas" title={canvas?.kind === "ui" ? "Descargar JSON" : "Descargar Markdown"} disabled={!canvas} onClick={download}><LuDownload /></button>
              <button type="button" aria-label="Cerrar Canvas" onClick={() => setOpen(false)}><LuX /></button>
            </div>
          </header>
          <div className="canvas-picker">
            <select aria-label="Seleccionar Canvas" value={canvas?.id ?? ""} onChange={(e) => { select(e.target.value); follow.current = true; }}>
              <option value="" disabled>Elige un documento</option>
              {canvases.map((row) => <option key={row.id} value={row.id}>{row.title}{row.persisted ? "" : " (temporal)"}</option>)}
            </select>
          </div>
          {error && <p role="alert" className="canvas-error">{error}</p>}
          {canvas ? (
            <>
              <div className="canvas-document-heading">
                <h3>{canvas.title}</h3>
                <span>{canvas.active_call ? "Escribiendo en vivo" : canvas.status === "interrupted" ? "Borrador parcial conservado" : canvas.persisted ? "Guardado" : "Temporal"} · r{canvas.revision}</span>
              </div>
              <div
                ref={viewport}
                className="canvas-document prose prose-sm max-w-none"
                onScroll={(e) => { const el = e.currentTarget; follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60; }}
              >
                <CanvasBody canvas={canvas} effects={effects} />
              </div>
              {notice && (
                <p role={notice.tone === "ok" ? "status" : "alert"} className={`${notice.tone === "ok" ? "canvas-notice" : "canvas-error"} flex items-center justify-between gap-2`}>
                  <span>{notice.text}</span>
                  <button type="button" className="inline-flex min-h-9 min-w-9 shrink-0 items-center justify-center rounded hover:bg-fg/10" onClick={dismiss} aria-label="Cerrar aviso del Canvas"><LuX /></button>
                </p>
              )}
            </>
          ) : (
            <div className="canvas-empty"><LuFileText /><h3>Un espacio para tus documentos</h3><p>Pide al Agente que cree un Canvas.</p></div>
          )}
        </section>
      )}
    </div>
  );
}
