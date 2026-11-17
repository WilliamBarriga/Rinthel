import { useState } from "react";
import type { UserPublic } from "@deck/contract";
import { guardMessage } from "./guard-message";
import { useUserDelete } from "./use-user-delete";

/**
 * Borrar usuario: says what goes with the user (every Sesión of theirs in Deck, retired first) and
 * needs a second, deliberate gesture (typing the username). On the own row it offers nothing and
 * says why. A refusal or a failure leaves the panel as it is.
 */
export function UserDelete({ user, self, onDeleted }: { user: UserPublic; self: boolean; onDeleted: () => Promise<void> | void }) {
  const { open, busy, error, openConfirm, confirm, cancel: cancelConfirm } = useUserDelete({ user, onDeleted });
  const [typed, setTyped] = useState("");
  const cancel = () => { cancelConfirm(); setTyped(""); };

  return (
    <section aria-label="Borrar usuario" className="mt-5 space-y-2 border-t border-line pt-4">
      <h3 className="text-xs font-medium text-fg-muted">Borrar usuario</h3>
      <button type="button" onClick={openConfirm} disabled={self || open} aria-describedby={self ? "delete-why" : undefined} className="rounded-xl border border-danger px-3 py-2 text-sm text-danger hover:bg-danger/5 disabled:opacity-50">Borrar usuario</button>
      {self && <p id="delete-why" className="text-xs text-fg-subtle">{guardMessage("self_lockout", "delete")}</p>}
      {open && !self && (
        <div role="region" aria-label="Confirmar borrado" className="space-y-2 rounded-lg border border-danger/40 p-3">
          <p className="text-xs text-fg-muted">Primero se retiran todas sus Sesiones de Deck, con su historial; después se borra la cuenta. No se puede deshacer.</p>
          <div className="space-y-1">
            <label htmlFor="delete-confirm" className="block text-xs font-medium text-fg-muted">{`Escribe ${user.username} para confirmar`}</label>
            <input id="delete-confirm" autoComplete="off" value={typed} onChange={(e) => setTyped(e.target.value)} className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-fg" />
            <button type="button" onClick={() => void confirm()} disabled={busy || typed !== user.username} className="rounded-xl bg-danger px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">Borrar definitivamente</button>
          </div>
          <button type="button" onClick={cancel} disabled={busy} className="block text-xs text-fg-muted hover:underline">Cancelar</button>
          {error && <p role="alert" className="text-xs text-danger">{error}</p>}
        </div>
      )}
    </section>
  );
}
