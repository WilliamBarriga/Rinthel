import { LuGlobe, LuX } from "react-icons/lu";
import { useSessionBrowser } from "./use-session-browser";

const RESIZE_STEP = 32;
const maxWidth = () => Math.max(320, Math.round(window.innerWidth * 0.7));

/**
 * A Session's browser (admin only): the toggle that lets its Agent drive the Instance browser, and the
 * live view of that browser beside the chat. The browser is shared by every admin Session; this is a
 * window on it, not a browser of its own. Nothing is drawn for a reader who may not see the browser.
 */
export function SessionBrowser({ sessionId, onFailure }: { sessionId: string; onFailure?: (error: unknown) => void }) {
  const browser = useSessionBrowser(sessionId, { onFailure });
  if (!browser.available) return null;
  const panelId = `session-browser-${sessionId}`;
  const max = maxWidth();
  return (
    <>
      <button type="button" className="session-browser-toggle" aria-expanded={browser.open} aria-controls={panelId} onClick={browser.toggleOpen}
        // Beside the open panel, never over its own header.
        style={browser.open ? { right: Math.min(browser.width, max) + 26 } : undefined}
        aria-label="Navegador de la Sesión" title="Navegador de la Sesión">
        <LuGlobe />{browser.enabled && <span>activo</span>}
      </button>
      {browser.open && (
        <div className="session-tools-resizer" role="separator" aria-label="Ancho de herramientas" aria-orientation="vertical"
          aria-valuemin={browser.minWidth} aria-valuemax={max} aria-valuenow={Math.min(browser.width, max)} tabIndex={0}
          onKeyDown={(event) => {
            if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
            event.preventDefault();
            browser.resize(event.key === "ArrowLeft" ? RESIZE_STEP : -RESIZE_STEP, max);
          }}
          onPointerDown={(event) => {
            const startX = event.clientX;
            const start = browser.width;
            const move = (e: PointerEvent) => browser.resize(start + (startX - e.clientX) - browser.width, max);
            const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
            window.addEventListener("pointermove", move);
            window.addEventListener("pointerup", up);
          }} />
      )}
      <aside id={panelId} aria-label="Navegador de la Sesión" hidden={!browser.open} className="session-tools" style={{ width: Math.min(browser.width, max) }}>
        {/* The way back sits on the left: the Canvas toggle floats over the right edge. */}
        <header className="session-tools-heading">
          <button type="button" onClick={browser.close} aria-label="Volver al chat" title="Cerrar panel y volver al chat"><LuX aria-hidden="true" /></button>
          <h3>Navegador de la Sesión</h3>
        </header>
        <label className="session-tools-option">
          <input type="checkbox" checked={browser.enabled} onChange={(e) => void browser.setEnabled(e.target.checked)} />
          El Agente puede usar el Instance browser en esta Sesión
        </label>
        <p className="session-tools-note">Solo una Sesión de un admin lo usa; el browser es el mismo para todas.</p>
        {browser.error && <p role="alert" className="session-tools-note text-red-500">{browser.error}</p>}
        <div className="session-tools-body">
          {!browser.running && <p className="session-tools-note">El Instance browser no está en marcha. Se arranca desde su pantalla de administración.</p>}
          {browser.running && browser.used && <iframe src="/browser-ui/" title="Navegador de la Sesión" allow="clipboard-read; clipboard-write; fullscreen" />}
        </div>
      </aside>
    </>
  );
}
