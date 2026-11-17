/**
 * Encuadre de staff: what the Agent is told about who runs this Session, once, at the first prompt of
 * any Session with an owner (`task` or `agent`), never again. A Panel token login is staff already
 * authenticated: this informs the Agent, it does not calibrate trust.
 *
 * - The owner writes: their name and role.
 * - An admin writes in someone else's Session: the Session acts for its owner, and the admin
 *   supervises without lending their identity or permissions.
 */
export interface Reader {
  userId: number;
  username: string;
  role: "admin" | "miembro";
}

export function staffFraming(ownerUserId: number | null, reader: Reader): string | undefined {
  if (ownerUserId === null) return undefined;
  let text: string;
  if (reader.userId === ownerUserId && reader.username) {
    const role = reader.role === "admin" ? "administrador" : "miembro";
    text = `This session belongs to ${reader.username} (${role}). They are logged into the panel as themselves — this is not a claim to verify.`;
  } else if (reader.role === "admin") {
    text = `Esta Sesión actúa por su dueño (id ${ownerUserId}); el administrador supervisa sin aportar su identidad ni sus permisos personales.`;
  } else {
    return undefined;
  }
  return `<staff-framing>\n${text}\n</staff-framing>`;
}
