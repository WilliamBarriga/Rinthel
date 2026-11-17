import { useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { LuX } from "react-icons/lu";
import type { UserCreate, UserPublic, UserUpdate } from "@deck/contract";
import { guardMessage } from "./guard-message";
import type { UserWrite } from "./use-users-admin";
import { newUserErrors, passwordError, PASSWORD_MIN_LENGTH, userPatch, type Field, type Role } from "./model/user-form";

const INPUT = "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-fg";

function FieldBox({ id, label, error, children }: { id: string; label: string; error?: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-xs font-medium text-fg-muted">{label}</label>
      {children}
      {error && <p id={`${id}-error`} role="alert" className="text-xs text-danger">{error}</p>}
    </div>
  );
}

/** What a refusal says, on the field it is about; the rest goes to the form. */
function fieldOf(result: Extract<UserWrite, { ok: false }>): [Field, string] {
  if (result.field) return [result.field, result.message];
  if (result.code === "username_taken") return ["username", "Ese nombre de usuario ya existe."];
  const guard = guardMessage(result.code, "demote");
  if (guard) return ["role", guard];
  return ["form", result.message];
}

/**
 * Side panel of Usuarios, in two modes: `user` set edits that user (name read-only, password
 * optional), no `user` creates one. It keeps what was typed when the daemon refuses, shows the
 * refusal on its field, and never receives or shows a password. Mount it with `key` = the user id,
 * so it starts clean for each one. The status and delete sections come as children.
 */
export function UserPanel({ user, self = false, closeTo, onCreate, onUpdate, children }: {
  user?: UserPublic;
  /** The user is the admin looking at the screen: the controls the guard would refuse go disabled. */
  self?: boolean;
  /** Where the close button goes (the table, with its filters). */
  closeTo: string;
  onCreate: (input: UserCreate) => Promise<UserWrite>;
  onUpdate: (id: number, patch: UserUpdate) => Promise<UserWrite>;
  children?: ReactNode;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const initialNotice = (location.state as { notice?: string } | null)?.notice ?? null;
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>(user?.role ?? "miembro");
  const [notes, setNotes] = useState(user?.notes ?? "");
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const [notice, setNotice] = useState<string | null>(initialNotice);
  const [busy, setBusy] = useState(false);
  const ownAdmin = self && user?.role === "admin";

  const patch: UserUpdate = user ? userPatch(user, { role, notes, password }) : {};
  const dirty = Object.keys(patch).length > 0;

  const submit = async () => {
    setNotice(null);
    if (!user) {
      const found = newUserErrors({ username, password });
      setErrors(found);
      if (Object.keys(found).length) return;
    } else {
      const error = passwordError(password, true);
      if (error) { setErrors({ password: error }); return; }
      if (!dirty) return;
    }
    setBusy(true);
    const result = user
      ? await onUpdate(user.id, patch)
      : await onCreate({ username: username.trim(), password, role, notes });
    setBusy(false);
    if (!result.ok) {
      const [field, message] = fieldOf(result);
      setErrors({ [field]: message });
      return;
    }
    setErrors({});
    setPassword("");
    if (!user) navigate(`/users/${result.user.id}${location.search}`, { replace: true, state: { notice: "Usuario creado" } });
    else setNotice("Cambios guardados");
  };

  return (
    <aside aria-label="Detalle de usuario" className="user-panel flex min-h-0 w-full shrink-0 flex-col overflow-y-auto border-l border-line bg-surface p-5 md:w-96">
      <div className="mb-4 flex items-center justify-between gap-2">
        <h2 className="truncate text-lg font-semibold">{user ? user.username : "Nuevo usuario"}</h2>
        <Link to={closeTo} aria-label="Cerrar panel" className="rounded-lg p-1.5 text-fg-subtle hover:bg-fg/5 hover:text-fg"><LuX className="h-4 w-4" /></Link>
      </div>
      {user?.disabled && <p className="mb-3 rounded-lg bg-fg/5 px-2 py-1 text-xs text-fg-subtle">Usuario desactivado</p>}
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        {!user && (
          <FieldBox id="user-name" label="Nombre de usuario" error={errors.username}>
            <input id="user-name" className={INPUT} value={username} autoComplete="off" onChange={(e) => setUsername(e.target.value)} />
          </FieldBox>
        )}
        <FieldBox id="user-password" label={user ? "Nueva contraseña" : "Contraseña"} error={errors.password}>
          <input id="user-password" type="password" className={INPUT} value={password} autoComplete="new-password" aria-invalid={!!errors.password} aria-describedby={`user-password-hint${errors.password ? " user-password-error" : ""}`} placeholder={user ? "Déjala vacía para no cambiarla" : undefined} onChange={(e) => setPassword(e.target.value)} />
          <p id="user-password-hint" className="text-xs text-fg-muted">Mínimo {PASSWORD_MIN_LENGTH} caracteres.{user ? " Déjala vacía para conservar la actual." : ""}</p>
        </FieldBox>
        <FieldBox id="user-role" label="Rol" error={errors.role}>
          <select id="user-role" className={INPUT} value={role} disabled={ownAdmin} aria-describedby={ownAdmin ? "role-why" : undefined} onChange={(e) => setRole(e.target.value as Role)}>
            <option value="miembro">miembro</option>
            <option value="admin">admin</option>
          </select>
          {ownAdmin && <p id="role-why" className="text-xs text-fg-subtle">No puedes quitarte el rol de admin a ti mismo: otro admin tendría que hacerlo.</p>}
        </FieldBox>
        <FieldBox id="user-notes" label="Notas">
          <textarea id="user-notes" rows={3} className={INPUT} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </FieldBox>
        {errors.form && <p role="alert" className="text-xs text-danger">{errors.form}</p>}
        {notice && <p role="status" className="text-xs text-ok">{notice}</p>}
        <button type="submit" disabled={busy || (!!user && !dirty)} className="rounded-xl bg-accent px-3 py-2 text-sm font-medium text-accent-fg transition hover:opacity-90 disabled:opacity-50">
          {user ? "Guardar" : "Crear usuario"}
        </button>
      </form>
      {children}
    </aside>
  );
}
