import type { UsersAdminConflictCode } from "../ports/users-admin";

/** What the admin tried to do when the guard of «sin admins / a sí mismo» refused. */
export type GuardVerb = "delete" | "disable" | "demote";

const MESSAGES: Record<"self_lockout" | "last_admin", Record<GuardVerb, string>> = {
  self_lockout: {
    delete: "No puedes borrarte a ti mismo: otro admin tendría que hacerlo.",
    disable: "Un admin no puede desactivarse a sí mismo.",
    demote: "Un admin no puede quitarse el rol a sí mismo.",
  },
  last_admin: {
    delete: "No se puede borrar al último admin activo: la Instance se quedaría sin admin.",
    disable: "La Instance no puede quedarse sin un admin activo.",
    demote: "La Instance no puede quedarse sin un admin activo.",
  },
};

/** The sentence for a guard refusal of `verb`, or `null` if `code` is not one of the guard's. */
export function guardMessage(code: UsersAdminConflictCode | null | undefined, verb: GuardVerb): string | null {
  return code === "self_lockout" || code === "last_admin" ? MESSAGES[code][verb] : null;
}
