import { useCallback, useRef } from "react";
import type { UserCreate, UserPublic, UserUpdate } from "@deck/contract";
import { useUsersAdminApi } from "../ports/context";
import { useRemote } from "../use-remote";
import { messageOf, PortError } from "../ports/http-errors";
import { PASSWORD_MIN_LENGTH, PASSWORD_TOO_SHORT } from "./model/user-form";
import { UsersAdminConflict, type UsersAdminConflictCode } from "../ports/users-admin";

/** What a write answers: the saved row, or a refusal the form can show on a field. */
export type UserWrite = { ok: true; user: UserPublic } | { ok: false; code: UsersAdminConflictCode | null; message: string; field?: "password" };

/** Translate the known password constraint without passing the daemon's rejected input to the view. */
function isShortPassword(error: unknown): boolean {
  if (!(error instanceof PortError) || error.status !== 422) return false;
  const detail = (error.body as { detail?: unknown } | undefined)?.detail;
  return Array.isArray(detail) && detail.some(issue =>
    issue !== null && typeof issue === "object" && Array.isArray(issue.loc) &&
    issue.loc.length === 2 && issue.loc[0] === "body" && issue.loc[1] === "password" &&
    issue.type === "string_too_short" && issue.ctx?.min_length === PASSWORD_MIN_LENGTH);
}

/**
 * Controller of Usuarios: the users through `usersAdminApi`. `createUser` and `updateUser`
 * re-read the list when they go through and answer with the saved row, or with the refusal
 * (`code` set for a typed 409) so a form keeps what was typed. A failed read becomes `error`
 * and a call to `onFailure`; nothing throws into a view.
 */
export function useUsersAdmin({ onFailure }: { onFailure?: (error: unknown) => void } = {}) {
  const api = useUsersAdminApi();
  const failure = useRef(onFailure);
  failure.current = onFailure;
  const read = useCallback(() => api.listUsers(), [api]);
  const remote = useRemote(read, { onFailure });
  const reload = useCallback(async () => { await remote.reload(); }, [remote.reload]);
  const error = remote.status === "error" ? messageOf(remote.error) : null;

  const write = useCallback(async (op: () => Promise<UserPublic>): Promise<UserWrite> => {
    try {
      const user = await op();
      await reload();
      return { ok: true, user };
    } catch (e) {
      if (isShortPassword(e)) return { ok: false, code: null, field: "password", message: PASSWORD_TOO_SHORT };
      if (e instanceof UsersAdminConflict) return { ok: false, code: e.code, message: e.message };
      failure.current?.(e);
      return { ok: false, code: null, message: messageOf(e) };
    }
  }, [reload]);

  const createUser = useCallback((user: UserCreate) => write(() => api.createUser(user)), [api, write]);
  const updateUser = useCallback((id: number, patch: UserUpdate) => write(() => api.updateUser(id, patch)), [api, write]);

  /** After a deletion: the list again, then `leave` (back to the table). */
  const afterDelete = useCallback(async (leave: () => void) => { await reload(); leave(); }, [reload]);

  return { status: remote.status, error, users: remote.data ?? [], createUser, updateUser, afterDelete };
}
