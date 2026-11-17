import { useBrowserPage } from "./use-browser-page";

const CONTAINER_LABEL = { absent: "sin instalar", stopped: "detenido", running: "en marcha", unavailable: "no disponible" } as const;
const MODE_LABEL = { docker: "contenedor (docker)", local: "Chrome local", external: "externo" } as const;
const button = "rounded-lg border border-line px-3 py-1.5 text-xs text-fg hover:bg-fg/5 disabled:opacity-40";

/**
 * The Instance browser (admin): install, start and stop it by hand, its login, the allowlist of
 * domains, the Sessions that may drive it, and its live view. Nothing stops it for being idle, so its
 * logins stay. Anyone else gets nothing of it.
 */
export function BrowserPage({ onFailure }: { onFailure?: (error: unknown) => void }) {
  const page = useBrowserPage({ onFailure });
  const { status } = page;

  if (page.forbidden) return <p role="alert" className="px-5 py-5 text-sm text-fg-muted">Solo el administrador puede usar el browser de la Instance.</p>;

  return (
    <div className="space-y-4 px-5 py-5">
      <header>
        <p className="ui-eyebrow">Administración</p>
        <h1 className="ui-title">Instance browser</h1>
        <p className="ui-description">
          Un solo navegador para toda la Instance, con sus sesiones iniciadas. Lo usan solo las Sesiones de un admin que lo tengan activado. Se arranca y se detiene a mano: nunca se apaga solo.
        </p>
      </header>
      {page.error && <p role="alert" className="text-xs text-red-500">{page.error}</p>}
      {!status ? <p role="status" className="text-sm text-fg-subtle">Cargando…</p> : (
        <>
          <section aria-label="Estado del browser" className="ui-card space-y-2 text-sm">
            <p>Modo: <strong>{MODE_LABEL[status.install.mode]}</strong> · Estado: <strong>{CONTAINER_LABEL[status.install.container]}</strong>{status.version && <> · {status.version}</>}</p>
            {status.install.pulling.active && <p role="status" className="text-xs text-fg-subtle">Descargando la imagen: {status.install.pulling.line}</p>}
            {status.install.pulling.error && <p className="text-xs text-red-500">La descarga falló: {status.install.pulling.error}</p>}
            {status.unprotected && <p role="alert" className="text-xs text-red-500">El browser está en marcha sin contraseña: cualquiera que llegue a su página usa sus sesiones iniciadas.</p>}
            {page.external && <p className="text-xs text-fg-subtle">Este browser se administra fuera de Deck: aquí solo se ve su estado.</p>}
            {page.needsPassword && (
              <div className="flex flex-wrap items-center gap-2">
                <label className="text-xs text-fg-muted">Contraseña de su página
                  <input aria-label="Contraseña del browser" type="text" value={page.password} onChange={(e) => page.setPassword(e.target.value)} className="ml-2 rounded-lg border border-line bg-canvas px-2 py-1" />
                </label>
                <button type="button" className={button} disabled={page.busy} onClick={() => void page.suggestPassword()}>Sugerir contraseña</button>
              </div>
            )}
            {!page.external && (
              <div className="flex flex-wrap gap-2">
                {status.install.container !== "running" && (
                  <button type="button" className={button} disabled={!page.canInstall || !status.install.available} onClick={() => void page.install()}>
                    {page.installed ? "Arrancar" : "Instalar"}
                  </button>
                )}
                {status.install.container === "running" && <button type="button" className={button} disabled={page.busy} onClick={() => void page.stop()}>Detener</button>}
                {page.installed && status.install.mode === "docker" && <button type="button" className={button} disabled={page.busy} onClick={() => void page.remove()}>Quitar (conserva las sesiones iniciadas)</button>}
              </div>
            )}
          </section>

          <section aria-label="Dominios permitidos" className="ui-card space-y-2 text-sm">
            <label htmlFor="browser-allowlist" className="block text-xs text-fg-muted">Dominios permitidos, uno por línea (vacío: sin restricción). Admite <code>*.ejemplo.com</code>.</label>
            <textarea id="browser-allowlist" value={page.allowlist} onChange={(e) => page.setAllowlist(e.target.value)} rows={4} className="w-full rounded-lg border border-line bg-canvas px-2 py-1 font-mono text-xs" />
            <button type="button" className={button} disabled={!page.dirty || page.busy} onClick={() => void page.saveAllowlist()}>Guardar dominios</button>
          </section>

          <section aria-label="Sesiones con browser" className="ui-card space-y-1 text-sm">
            <p className="text-xs text-fg-muted">Sesiones que lo tienen activado</p>
            {status.sessions.length === 0 ? <p className="text-xs text-fg-subtle">Ninguna.</p> : (
              <ul className="list-disc pl-5 text-xs">{status.sessions.map((s) => <li key={s.id}>{s.title}</li>)}</ul>
            )}
            {status.pages.length > 0 && (
              <>
                <p className="pt-2 text-xs text-fg-muted">Pestañas abiertas</p>
                <ul className="list-disc pl-5 text-xs">{status.pages.map((p, i) => <li key={`${p.url}-${i}`}>{p.title || p.url}</li>)}</ul>
              </>
            )}
          </section>

          {status.running && (
            <section aria-label="Vista del browser" className="space-y-2">
              {page.embeddable ? (
                <>
                  <button type="button" className={button} aria-expanded={page.shown} onClick={page.toggleShown}>{page.shown ? "Ocultar la vista" : "Mostrar la vista"}</button>
                  {page.shown && <iframe src={page.uiUrl} title="Instance browser" className="h-[70dvh] w-full rounded-lg border border-line" allow="clipboard-read; clipboard-write; fullscreen" />}
                </>
              ) : (
                <a href={page.uiUrl} target="_blank" rel="noreferrer" className="text-xs text-accent underline">Abrir la vista del browser (HTTPS)</a>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
