import { ModelPicker } from "../models/ModelPicker";
import { VoiceModels } from "../models/VoiceModels";

/** Ajustes of the Instance (admin): the Local model every Session talks to, and the Instance's voice. */
export function SettingsPage() {
  return (
    <div className="space-y-6 px-5 py-5">
      <section className="space-y-4">
        <header>
          <p className="ui-eyebrow">Ajustes</p>
          <h1 className="ui-title">Local model</h1>
          <p className="ui-description">Todas las Sesiones usan el mismo Local model y pasan al nuevo en su próximo turno. No se puede cambiar mientras hay turnos en curso.</p>
        </header>
        <ModelPicker />
      </section>
      <section className="space-y-4">
        <header>
          <h2 className="ui-title">Voz de la Instance</h2>
          <p className="ui-description">Los servicios de voz corren en el host (solo Linux). Encenderlos aquí los arranca; apagarlos los detiene, y la voz deja de aparecer en las Sesiones.</p>
        </header>
        <VoiceModels />
      </section>
    </div>
  );
}
