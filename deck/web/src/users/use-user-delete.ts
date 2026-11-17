import { useState } from "react";
import type { UserPublic } from "@deck/contract";
import { useReportExpired } from "../failure-context";
import { useUsersAdminApi } from "../ports/context";
import { messageOf } from "../ports/http-errors";
import { UsersAdminConflict, UsersAdminSessionsNotRetired } from "../ports/users-admin";
import { guardMessage } from "./guard-message";

/** What the admin reads when Deck could not retire the user's Sesiones: nothing was deleted. */
export const SESSIONS_NOT_RETIRED = "No se pudieron retirar sus Sesiones de Deck: el usuario no se borró. Vuelve a intentarlo.";

/** Controller of «Borrar usuario»: the confirmation and the deletion; a refusal leaves the panel as it is. */
export function useUserDelete({ user, onDeleted }: { user: UserPublic; onDeleted: () => Promise<void> | void }) {
  const api = useUsersAdminApi();
  const reportExpired = useReportExpired();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.deleteUser(user.id);
    } catch (e) {
      reportExpired(e);
      if (e instanceof UsersAdminSessionsNotRetired) setError(SESSIONS_NOT_RETIRED);
      else setError((e instanceof UsersAdminConflict && guardMessage(e.code, "delete")) || messageOf(e));
      setBusy(false);
      return;
    }
    await onDeleted();
  };
  const openConfirm = () => { setOpen(true); setError(null); };
  const cancel = () => { setOpen(false); setError(null); };
  return { open, busy, error, openConfirm, confirm, cancel };
}
