/**
 * La SOUL de la Instance (`/api/agent/instance-soul`): el `SOUL.md` que cargan las Sesiones de todos
 * los miembros. Cualquiera la lee; solo el admin la edita.
 */
export interface InstanceSoul {
  name: "SOUL.md";
  /** False mientras nadie la definió (INSTALL la siembra, así que normalmente existe). */
  exists: boolean;
  content: string;
  /** Si quien pregunta puede reemplazarla: el admin sí, el miembro la ve de solo lectura. */
  editable: boolean;
}
