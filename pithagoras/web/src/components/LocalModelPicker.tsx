import { useEffect, useRef, useState } from "react";
import { api } from "../api";

type Catalogue = {active: string | null; busy: boolean; models: {key: string; name: string; available: boolean}[]};
export function LocalModelPicker({running, onChanged, onAvailable}: {running: boolean; onChanged: () => void; onAvailable: (value: boolean) => void}) {
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const refresh = () => api.localModels().then(value => { setCatalogue(value); onAvailable(value.models.length > 0); }).catch(() => {});
  useEffect(() => { refresh(); }, []);
  useEffect(() => {
    if (!open) return;
    refresh();
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const escape = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', close); document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', escape); };
  }, [open]);
  if (!catalogue?.models.length) return null;
  const active = catalogue.models.find(m => m.key === catalogue.active);
  return <div className="relative" ref={ref}>
    <button type="button" aria-haspopup="menu" aria-expanded={open} disabled={busy}
      onClick={() => setOpen(!open)} className="rounded-lg px-2 py-1.5 text-fg hover:bg-fg/5 disabled:opacity-60">
      {busy ? 'Cargando modelo…' : `${active?.name || 'Elegir modelo local'} ▾`}
    </button>
    {error && <p role="alert" className="max-w-72 text-red-400">{error}</p>}
    {open && <div role="menu" aria-label="Modelo local" className="absolute bottom-full left-0 z-50 mb-2 w-72 rounded-xl border border-line bg-surface p-2 shadow-pop">
      <p className="px-2 py-1 text-xs text-fg-subtle">Modelo local</p>
      {catalogue.models.map(model => <button key={model.key} type="button" role="menuitemradio" aria-checked={catalogue.active === model.key}
        disabled={busy || running || catalogue.busy || !model.available}
        className="flex w-full items-center justify-between rounded-lg px-2 py-3 text-left text-sm text-fg hover:bg-raised disabled:opacity-50"
        onClick={async () => {
          setBusy(true); setError('');
          try { setCatalogue(await api.switchLocalModel(model.key)); onChanged(); setOpen(false); }
          catch (e) { setError(e instanceof Error ? e.message : 'No se pudo cambiar el modelo'); await refresh(); }
          finally { setBusy(false); }
        }}>
        <span>{model.name}{!model.available && ' · Sin descargar'}</span><span>{catalogue.active === model.key ? '✓' : ''}</span>
      </button>)}
      <p className="px-2 py-2 text-xs text-fg-subtle" role="status">{busy ? 'Espera mientras se carga. Puede tardar unos minutos.' : running ? 'Espera a que termine la respuesta.' : 'Se aplica a los chats locales de este portal.'}</p>
    </div>}
  </div>;
}
