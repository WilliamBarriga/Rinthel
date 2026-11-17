import { useId } from "react";
import { useBrandingUpload } from "./use-branding-upload";
import type { Branding, Preferences } from "@deck/contract";
const selects = [
  ["density", "Densidad", [["compact", "Compacto"], ["comfortable", "Cómodo"], ["spacious", "Amplio"]]],
  ["material", "Superficies", [["soft", "Suaves"], ["flat", "Planas"]]],
  ["tone", "Tono del espacio", [["neutral", "Neutro"], ["warm", "Cálido"], ["cool", "Frío"]]],
  ["depth", "Profundidad", [["subtle", "Con sombras"], ["none", "Sin sombras"]]],
  ["font", "Tipografía", [["system", "Sistema"], ["humanist", "Humanista"], ["editorial", "Lectura editorial"]]],
  ["readingWidth", "Ancho de lectura", [["focused", "Concentrado"], ["balanced", "Equilibrado"], ["wide", "Amplio"]]],
  ["listStyle", "Presentación de filas", [["list", "Continuas"], ["separated", "Separadas"]]],
] as const;
const ranges = [["radius", "Redondeado", 0, 24, 1], ["fontSize", "Tamaño de texto", 13, 20, 1], ["lineHeight", "Interlineado", 1.4, 2, .05], ["navWidth", "Ancho de navegación", 180, 320, 10]] as const;
const toggles = [["contrast", "Mayor contraste"], ["reducedMotion", "Reducir movimiento"]] as const;
const help: Partial<Record<keyof Preferences, string>> = {
  density: "Compacto reduce la separación; Amplio da más aire a tarjetas, formularios y filas. Compáralos en la muestra de abajo.",
  material: "Suaves separa el fondo y los paneles con dos rellenos; Planas los unifica. Los bordes se conservan.",
  tone: "Matiz cálido o frío en las superficies del contenido; independiente de la marca.",
  depth: "Añade o quita las sombras de paneles y tarjetas. Los indicadores de selección y foco se conservan.",
  font: "Sistema y Humanista en la interfaz; Editorial en respuestas y fragmentos de documentos.",
  readingWidth: "Límite de ancho de respuestas y fragmentos. En pantallas estrechas manda el espacio disponible.",
  listStyle: "Separación visual de las filas de Sesiones.",
  radius: "Esquinas de tarjetas, paneles y controles de apariencia, en píxeles.",
  fontSize: "Texto de la interfaz y contenido de lectura, en píxeles; títulos y ayudas conservan su jerarquía.",
  lineHeight: "Espacio entre líneas en respuestas y fragmentos de documentos; no cambia las etiquetas de controles.",
  navWidth: "Ancho de la barra lateral en escritorio Equilibrado y Operación; Enfoque y móvil usan su ancho disponible.",
  contrast: "Refuerza textos secundarios y separadores en el tema actual.",
  reducedMotion: "Desactiva animaciones y transiciones; la reducción del dispositivo siempre se respeta.",
};
const groups = [
  { title: "Interfaz y superficies", keys: ["density", "material", "depth", "radius"] },
  { title: "Lectura", keys: ["font", "fontSize", "lineHeight", "readingWidth", "listStyle", "contrast", "reducedMotion"] },
  { title: "Navegación y contexto", keys: ["navWidth"] },
];
export function AppearanceControls({ value, onChange, isAdmin = false, section }: { isAdmin?: boolean; section?: string; value: Preferences; onChange: (patch: Partial<Preferences>) => void }) {
  const prefix = useId();
  return <>{groups.filter(group => !section || group.title === section).map(group => <section className="appearance-control-group" key={group.title} aria-label={group.title}>
    <h3 className="ui-label">{group.title}</h3>
    <div className="appearance-fields">
      {selects.filter(([key]) => group.keys.includes(key)).map(([key, label, options]) => <label key={key}>{label}<select aria-label={label} aria-describedby={`${prefix}-${key}`} value={value[key]} onChange={e => onChange({ [key]: e.target.value })}>{options.map(([v, text]) => <option key={v} value={v}>{text}</option>)}</select><small id={`${prefix}-${key}`}>{help[key]}</small></label>)}
      {ranges.filter(([key]) => group.keys.includes(key)).map(([key, label, min, max, step]) => <label key={key}>{label}<input aria-label={label} aria-describedby={`${prefix}-${key}`} type="range" min={min} max={max} step={step} value={value[key]} onChange={e => onChange({ [key]: Number(e.target.value) })} /><output>{value[key]}</output><small id={`${prefix}-${key}`}>{help[key]}</small></label>)}
      {toggles.filter(([key]) => group.keys.includes(key)).map(([key, label]) => <div key={key}><label className="appearance-toggle"><input aria-label={label} aria-describedby={`${prefix}-${key}`} type="checkbox" checked={value[key]} onChange={e => onChange({ [key]: e.target.checked })} />{label}</label><small id={`${prefix}-${key}`}>{help[key]}</small></div>)}
    </div>
  </section>)}</>;
}

/** Uses the same card and reading rules as the current workspace. */
export function AppearanceSample() {
  return <section aria-label="Muestra visual" className="ui-card appearance-sample">
    <h3 className="ui-label">Muestra visual · sin datos guardados</h3>
    <p className="ui-description">Observa superficies, tonos, sombras, radio y lectura. Esta muestra no guarda datos.</p>
    <div className="appearance-sample-surface"><div className="appearance-reading"><p>Una lectura clara deja espacio para comprender y verificar las respuestas. Este texto de ejemplo usa la misma tipografía, tamaño, interlineado y límite de ancho que el contenido de lectura.</p></div></div>
  </section>;
}
export function BrandingControls({ value, onChange }: { value: Branding; onChange: (patch: Partial<Branding>) => void }) {
  const { error, upload } = useBrandingUpload(onChange);
  const logoSizes = [[28, "Discreto"], [36, "Normal"], [44, "Destacado"]] as const;
  return <div className="appearance-fields">
    {error && <p role="alert">{error}</p>}
    <label>Nombre de instalación<input value={value.name} maxLength={80} onChange={e => onChange({ name: e.target.value })} /></label>
    <label>Descripción de instalación<input value={value.tagline} maxLength={160} onChange={e => onChange({ tagline: e.target.value })} /></label>
    <label className="appearance-toggle"><input type="checkbox" checked={value.logo} onChange={e => onChange({ logo: e.target.checked })} />Mostrar logo</label>
    <label>Tamaño de logo<select aria-label="Tamaño de logo" value={value.logoSize} onChange={e => onChange({ logoSize: Number(e.target.value) })}>{!logoSizes.some(([size]) => size === value.logoSize) && <option value={value.logoSize}>Actual · {value.logoSize} px</option>}{logoSizes.map(([size, label]) => <option key={size} value={size}>{label} · {size} px</option>)}</select></label>
    <div><label>Logo claro<input type="file" accept="image/png,image/jpeg,image/webp" onChange={e => void upload(e.target.files?.[0], "logoLight")} /></label><p className="ui-description">Se usa en todos los temas.</p>{value.logoLight && <img className="appearance-logo-preview" src={value.logoLight} alt="Vista previa del logo claro" />}<button onClick={() => onChange({ logoLight: "" })}>Quitar logo claro</button></div>
  </div>;
}
