import { createContext, useContext, useId, useState, type ReactNode } from "react";
import type { Preferences } from "@deck/contract";
import { defaultBranding } from "../../../shared/appearance.mjs";
import { useAppearanceController } from "./use-appearance-controller";
import { AppearanceEffects } from "./AppearanceEffects";
import { ThemeSwitcher } from "../components/ThemeSwitcher";
import { ThemePreferenceContext } from "../theme";
import { AppearanceControls, AppearanceSample, BrandingControls } from "./controls";
import { PaletteControls } from "./PaletteControls";
import { LuCheck, LuCircleCheck, LuSave } from "react-icons/lu";
export type Layout = Preferences["layout"];
export const OPTIONS: { value: Layout; label: string; description: string }[] = [
  { value: "balanced", label: "Equilibrado", description: "Barra lateral, paneles separados y espacio cómodo entre secciones." },
  { value: "operation", label: "Operación", description: "Panel de herramientas en cuadrícula, secciones horizontales y mesa de trabajo amplia." },
];
type AppearanceState = ReturnType<typeof useAppearanceController>;
const AppearanceContext = createContext<AppearanceState | null>(null);
export const useAppearance = () => useContext(AppearanceContext);
/** Authenticated owner mounts once; presentation never keys resources. */
export function AppearanceProvider({ children, isAdmin = false }: { children: ReactNode; isAdmin?: boolean }) {
  const value = useAppearanceController(isAdmin);
  return <ThemePreferenceContext.Provider value={{ theme: value.preferences.theme, setTheme: value.setTheme, editable: isAdmin }}><AppearanceContext.Provider value={value}><AppearanceEffects />{children}</AppearanceContext.Provider></ThemePreferenceContext.Provider>;
}
export function InstallationBrand() {
  const appearance = useAppearance();
  const brand = appearance?.branding ?? defaultBranding;
  const logo = brand.logoLight;
  return <><span className="installation-logo" hidden={!brand.logo}>{<img src={logo || "/logo-192.png"} alt="" style={{ width: brand.logoSize, height: brand.logoSize }} draggable={false} />}</span><div className="min-w-0"><h1 className="text-sm font-semibold tracking-tight text-fg">{brand.name}</h1>{brand.tagline && <p className="text-xs text-fg-muted break-words">{brand.tagline}</p>}</div></>;
}
function LayoutPreview({ layout }: { layout: Layout }) {
  return <span aria-hidden="true" className={`layout-preview layout-preview-${layout}`}>
    <span className="layout-preview-nav">{layout === "operation" && [0, 1, 2, 3].map(cell => <span key={cell} />)}</span>
    <span className="layout-preview-body"><span /><span /><span /></span>
  </span>;
}
export function AppearancePanel() {
  const a = useAppearance(); const [name, setName] = useState("");
  const [tab, setTab] = useState("Estilo"); const prefix = useId();
  if (!a) return null;
  const tabs = ["Estilo", ...(a.isAdmin ? ["Marca"] : []), "Lectura", "Paneles", "Perfiles"];
  const activeTab = tabs.includes(tab) ? tab : "Estilo";
  const editingBrand = activeTab === "Marca";
  const dirty = editingBrand ? a.brandingDirty : a.preferencesDirty;
  const saveStatus = a.loading ? "Cargando configuración…" : !a.readReady ? "Guardado no disponible" : a.busy ? "Guardando…" : dirty ? "Vista previa · cambios sin aplicar" : "Sin cambios pendientes";
  const panelProps = (name: string) => ({ role: "tabpanel", id: `${prefix}-panel-${name}`, "aria-labelledby": `${prefix}-tab-${name}`, hidden: activeTab !== name, tabIndex: 0 });
  return <section aria-label="Personalización" className="appearance-panel" aria-busy={a.busy}>
    <header className="appearance-heading"><div><h2 className="ui-title">Apariencia</h2><p className="ui-description">Prueba los cambios antes de aplicarlos.</p></div><span className="appearance-scope">{editingBrand ? "Compartida · administración" : "Preferencias personales"}</span></header>
    {a.error && <p role="alert" className="appearance-error">{a.error}</p>}{!a.loading && !a.readReady && <p className="ui-description">Vista previa local disponible. Aplicar, guardar perfiles y guardar marca están deshabilitados hasta cargar la configuración.</p>}
    <div role="tablist" aria-label="Secciones de Personalización" className="appearance-tabs">{tabs.map((name, index) => <button key={name} type="button" role="tab" id={`${prefix}-tab-${name}`} aria-controls={`${prefix}-panel-${name}`} aria-selected={activeTab === name} tabIndex={activeTab === name ? 0 : -1} onClick={() => setTab(name)} onKeyDown={event => {
      const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : event.key === "ArrowRight" ? (index + 1) % tabs.length : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length : -1;
      if (next < 0) return;
      event.preventDefault(); setTab(tabs[next]);
      document.getElementById(`${prefix}-tab-${tabs[next]}`)?.focus();
    }}>{name}</button>)}</div>
    <div {...panelProps("Estilo")}><fieldset disabled={a.loading || a.busy}><legend className="ui-label">Estilo personal</legend>
      <p className="ui-description">Elige cómo quieres trabajar.</p>
      <div role="radiogroup" aria-label="Estilo de distribución" className="appearance-options">{OPTIONS.map(option => <label key={option.value} className="ui-choice appearance-layout-choice"><LayoutPreview layout={option.value} /><span className="appearance-option-title"><input type="radio" name="appearance-layout" checked={a.preferences.layout === option.value} onChange={() => a.change({ layout: option.value })} /><strong>{option.label}</strong>{a.preferences.layout === option.value && <LuCheck aria-hidden="true" />}</span><span>{option.description}</span></label>)}</div>
      <p className="ui-description">Los colores y el tema los administra el administrador. Cambiar de estilo conserva tu trabajo y la paleta compartida.</p>
      <AppearanceControls section="Interfaz y superficies" isAdmin={a.isAdmin} value={a.preferences} onChange={a.change} />
      <AppearanceSample />
    </fieldset></div>
    <div {...panelProps("Lectura")}><fieldset disabled={a.loading || a.busy}><legend>Lectura</legend><p className="ui-description">Ajusta el texto y el contraste para leer con comodidad. Puedes comprobar el resultado en la muestra.</p><AppearanceControls section="Lectura" isAdmin={a.isAdmin} value={a.preferences} onChange={a.change} /><AppearanceSample /></fieldset></div>
    <div {...panelProps("Paneles")}><fieldset disabled={a.loading || a.busy}><legend>Paneles</legend><p className="ui-description">Elige cómo se ve la navegación.</p><AppearanceControls section="Navegación y contexto" isAdmin={a.isAdmin} value={a.preferences} onChange={a.change} />
    </fieldset></div>
    <div {...panelProps("Perfiles")}><fieldset disabled={a.loading || a.busy}><legend>Perfiles personales</legend>
      <p className="ui-description">Guarda combinaciones de tus preferencias para volver a usarlas. La marca de instalación se gestiona por separado.</p><p>{a.profiles.length} de 10 combinaciones guardadas.</p><label>Nombre del perfil<input value={name} maxLength={60} onChange={e => setName(e.target.value)} /></label><button disabled={!a.readReady} onClick={() => void a.saveProfile(name)}>Guardar perfil</button>
      <ul>{a.profiles.map(profile => <li className="appearance-profile-row" key={profile.name}><span>{profile.name}</span><button onClick={() => a.change(profile.preferences)}>Usar {profile.name}</button><button disabled={!a.readReady} onClick={() => void a.removeProfile(profile.name)}>Quitar {profile.name}</button></li>)}</ul>
      <details><summary>Ver configuración personal</summary><label>Configuración personal<textarea className="appearance-config" readOnly rows={12} value={a.personalConfig} onFocus={event => event.currentTarget.select()} /></label><button disabled={!a.readReady} onClick={() => void a.copyPersonal()}>Copiar configuración personal</button></details>
    </fieldset></div>
    {a.isAdmin && <div {...panelProps("Marca")}><fieldset disabled={a.loading || a.busy}><legend>Marca de instalación · administración</legend><p className="ui-description">Compartida por todos los usuarios. Se guarda por separado de tus preferencias.</p><BrandingControls value={a.branding} onChange={a.changeBrand} />
      <div className="ui-card"><h3 className="ui-label">Tema base de la Instance</h3><ThemeSwitcher expanded /></div>
      {!a.branding.palette && <p className="ui-description">Tus colores anteriores siguen siendo personales hasta compartirlos. <button type="button" onClick={a.shareCurrentPalette}>Compartir colores actuales</button></p>}
      <PaletteControls value={a.preferences} onChange={a.changePalette} />
      <label>Tono del espacio<select aria-label="Tono del espacio" value={a.preferences.tone} onChange={event => a.changePalette({ tone: event.target.value as Preferences["tone"] })}><option value="neutral">Neutro</option><option value="warm">Cálido</option><option value="cool">Frío</option></select></label>
    </fieldset></div>}
    <footer className="appearance-savebar">
      <div role="status" aria-live="polite" className="appearance-save-state" data-pending={dirty}>
        <p>{!dirty && a.readReady && !a.busy && <LuCircleCheck aria-hidden="true" />}{saveStatus}</p>
        {a.notice && <p className="appearance-save-notice">{a.notice}</p>}
      </div>
      <div className="appearance-actions">
        <button className="btn-primary" disabled={a.loading || a.busy || !a.readReady} onClick={() => void (editingBrand ? a.applyBrand() : a.apply())}><LuSave aria-hidden="true" />{editingBrand ? "Guardar marca de instalación" : "Aplicar preferencias"}</button>
        <button className="appearance-secondary-action" disabled={a.loading || a.busy} onClick={editingBrand ? a.undoBrand : a.undo}>{editingBrand ? "Deshacer marca" : "Deshacer preferencias"}</button>
        <button className="appearance-secondary-action" disabled={a.loading || a.busy} onClick={editingBrand ? a.resetBrand : a.reset}>{editingBrand ? "Restaurar marca" : "Restaurar preferencias"}</button>
      </div>
    </footer>
  </section>;
}
