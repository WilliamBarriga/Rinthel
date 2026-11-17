import { ModelPicker } from "../models/ModelPicker";

/** Ajustes of the Instance (admin): the Local model every Session talks to. */
export function SettingsPage() {
  return (
    <div className="space-y-4 px-5 py-5">
      <header>
        <p className="ui-eyebrow">Ajustes</p>
        <h1 className="ui-title">Local model</h1>
        <p className="ui-description">Todas las Sesiones usan el mismo Local model y pasan al nuevo en su próximo turno. No se puede cambiar mientras hay turnos en curso.</p>
      </header>
      <ModelPicker />
    </div>
  );
}
