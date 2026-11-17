import type { Role, UserPublic, UserUpdate } from "@deck/contract";

export type { Role } from "@deck/contract";
export type Field = "username" | "password" | "role" | "notes" | "form";
export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_TOO_SHORT = `La contraseña debe tener al menos ${PASSWORD_MIN_LENGTH} caracteres.`;

/** Matches the daemon's minimum in Unicode code points; whitespace is part of the password. */
export function passwordError(password: string, optional = false): string | undefined {
  if (!password) return optional ? undefined : "Escribe una contraseña.";
  if ([...password].length < PASSWORD_MIN_LENGTH) return PASSWORD_TOO_SHORT;
  return undefined;
}

/** What the panel's fields hold, before any rule runs. */
export interface UserDraft {
  role: Role;
  notes: string;
  password: string;
}

/** The fields that differ from the saved user; empty means nothing to save. */
export function userPatch(user: UserPublic, draft: UserDraft): UserUpdate {
  const patch: UserUpdate = {};
  if (draft.role !== user.role) patch.role = draft.role;
  if (draft.notes !== user.notes) patch.notes = draft.notes;
  if (draft.password) patch.password = draft.password;
  return patch;
}

/** What stops a new user from being created, by field; empty means it can go. */
export function newUserErrors(input: { username: string; password: string }): Partial<Record<Field, string>> {
  const found: Partial<Record<Field, string>> = {};
  if (!input.username.trim()) found.username = "Escribe un nombre.";
  const error = passwordError(input.password);
  if (error) found.password = error;
  return found;
}
