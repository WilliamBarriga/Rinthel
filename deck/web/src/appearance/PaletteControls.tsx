import type { Preferences } from "@deck/contract";
import { LuCheck } from "react-icons/lu";

const presets = [
  { name: "Bosque", paletteAccent: "#34d399", paletteBackground: "#101e19", paletteSurface: "#192e25", paletteNavigation: "#244b40" },
  { name: "Océano", paletteAccent: "#38bdf8", paletteBackground: "#101c2d", paletteSurface: "#192c43", paletteNavigation: "#174369" },
  { name: "Ciruela", paletteAccent: "#d8b4fe", paletteBackground: "#211429", paletteSurface: "#32203e", paletteNavigation: "#4e365d" },
  { name: "Arena", paletteAccent: "#8b5225", paletteBackground: "#f5efe5", paletteSurface: "#fffaf1", paletteNavigation: "#e4d6bd" },
];
const colors = [
  ["paletteAccent", "Acciones y enlaces"], ["paletteBackground", "Color base del espacio"],
  ["paletteSurface", "Matiz de paneles y tarjetas"], ["paletteNavigation", "Navegación"],
] as const;

export function PaletteControls({ value, onChange }: {
  value: Preferences; onChange: (patch: Partial<Preferences>) => void;
}) {
  const mode = value.paletteMode ?? "theme";
  return <section className="appearance-palette" aria-label="Paleta y transparencia">
    <h3 className="ui-label">Paleta de toda la interfaz</h3>
    <p className="ui-description">Los colores de la Instance dan origen a una paleta armonizada. El tema base define claro u oscuro; fondos y paneles usan tonos suaves y el texto adapta su contraste.</p>
    <label>Origen de los colores<select aria-label="Origen de los colores" value={mode} onChange={event => onChange({ paletteMode: event.target.value as Preferences["paletteMode"] })}>
      <option value="theme">Tema base</option><option value="brand">Colores de la marca</option><option value="custom">Paleta personalizada de la Instance</option>
    </select></label>
    {mode === "brand" && <p className="ui-description">El color principal de Marca da tono al sitio completo; su color de navegación se aplica a la barra. La luminosidad sigue el tema base.</p>}
    {mode === "custom" && <>
      <div className="appearance-palette-presets" aria-label="Paletas de partida">{presets.map(({ name, ...palette }) => {
        const selected = colors.every(([key]) => value[key] === palette[key]);
        return <button className="appearance-palette-preset" type="button" key={name} aria-pressed={selected} onClick={() => onChange(palette)}><span className="appearance-palette-sample" aria-hidden="true" style={{ background: palette.paletteSurface }}><span style={{ background: palette.paletteNavigation }} /><span style={{ background: palette.paletteAccent }} /></span><span>{name}</span>{selected && <LuCheck aria-hidden="true" />}</button>;
      })}</div>
      <div className="appearance-fields">{colors.map(([key, label]) => <label key={key}>{label}<input aria-label={label} type="color" value={value[key]} onChange={event => onChange({ [key]: event.target.value })} /><span className="appearance-color-value">{value[key]}</span></label>)}</div>
      <p className="ui-description">Los colores de los selectores son la base, no el relleno literal de áreas grandes. Así evitamos fondos saturados y mantenemos una lectura cómoda.</p>
    </>}
    <div className="appearance-effective-palette" aria-label="Colores aplicados"><span style={{ background: "rgb(var(--content-canvas))", color: "rgb(var(--content-fg))" }}>Fondo aplicado</span><span style={{ background: "rgb(var(--content-surface))", color: "rgb(var(--content-fg))" }}>Panel aplicado</span></div>
    <label className="appearance-transparency">Transparencia de paneles<input aria-label="Transparencia de paneles" type="range" min="0" max="60" step="5" value={value.transparency ?? 0} disabled={value.contrast} onChange={event => onChange({ transparency: Number(event.target.value) })} /><output>{value.transparency ?? 0}%</output><small>Deja ver el fondo a través de los paneles. El texto y los controles permanecen opacos. Mayor contraste desactiva este efecto.</small></label>
    <p className="ui-description">Guardar marca de instalación aplica estos colores a todos los usuarios. Los perfiles personales conservan distribución y lectura.</p>
  </section>;
}
