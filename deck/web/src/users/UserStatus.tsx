import { useState } from "react";
import type { UserPublic, UserUpdate } from "@deck/contract";
import { guardMessage } from "./guard-message";
import type { UserWrite } from "./use-users-admin";

/**
 * Desactivar / reactivar, applied at once (not part of the panel's Guardar). On the own row the
 * button is disabled with its reason; any other refusal is the daemon's 409.
 */
export function UserStatusSection({ user, self, onUpdate }: {
  user: UserPublic;
  self: boolean;
  onUpdate: (id: number, patch: UserUpdate) => Promise<UserWrite>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    setBusy(true);
    setError(null);
    const result = await onUpdate(user.id, { disabled: !user.disabled });
    setBusy(false);
    if (!result.ok) setError(guardMessage(result.code, "disable") ?? result.message);
  };
  const blocked = self && !user.disabled;
  return (
    <section aria-label="Estado de la cuenta" className="mt-5 space-y-2 border-t border-line pt-4">
      <h3 className="text-xs font-medium text-fg-muted">Estado de la cuenta</h3>
      {user.disabled
        ? <p className="text-xs text-fg-subtle">Reactivarlo le devuelve el acceso.</p>
        : <p className="text-xs text-fg-subtle">Desactivarlo corta su acceso y cierra sus sesiones del panel; no borra nada.</p>}
      <button type="button" onClick={() => void run()} disabled={busy || blocked} aria-describedby={blocked ? "status-why" : undefined} className="rounded-xl border border-line px-3 py-2 text-sm hover:bg-fg/5 disabled:opacity-50">
        {user.disabled ? "Reactivar usuario" : "Desactivar usuario"}
      </button>
      {blocked && <p id="status-why" className="text-xs text-fg-subtle">No puedes desactivarte a ti mismo: otro admin tendría que hacerlo.</p>}
      {error && <p role="alert" className="text-xs text-danger">{error}</p>}
    </section>
  );
}
