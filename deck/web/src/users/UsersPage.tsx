import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { LuPlus } from "react-icons/lu";
import { UserDelete } from "./UserDelete";
import { UserPanel } from "./UserPanel";
import { UserStatusSection } from "./UserStatus";
import { UsersTable } from "./UsersTable";
import { useUsersAdmin } from "./use-users-admin";

const SELECT = "rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-fg";

/**
 * «Usuarios» (admin only; the guard of the navigation registry covers it). Routes: `/users`
 * (table), `/users/new` (panel in create mode), `/users/:id` (panel open). Filters live in the
 * query string (`q`, `estado`), so a link keeps them and opening or closing the panel does not
 * reset them. The panel closes with Back or its close link.
 */
export function UsersPage({ onFailure, username }: { onFailure: (error: unknown) => void; username?: string }) {
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  // Read from the path, not `useParams`: the literal `/users/new` route has no `:id`.
  const id = pathname.split("/")[2];
  const [params, setParams] = useSearchParams();
  const { status, error, users, createUser, updateUser, afterDelete } = useUsersAdmin({ onFailure });
  const isSelf = (u: { username: string }) => !!username && u.username === username;

  const q = params.get("q") ?? "";
  const estado = params.get("estado") ?? "";
  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const shown = users.filter((u) =>
    u.username.toLowerCase().includes(q.trim().toLowerCase())
    && (!estado || (estado === "desactivado") === u.disabled));
  const selected = id && id !== "new" ? users.find((u) => String(u.id) === id) : undefined;
  const onlyAdmin = status === "ready" && users.length <= 1;

  return (
    <div className="admin-workspace users-workspace flex min-h-0 flex-1 flex-col">
      <div className="users-columns flex min-h-0 flex-1">
      <div className="users-directory min-w-0 flex-1 overflow-y-auto">
        <div className="admin-heading flex items-center justify-between gap-3 px-5 pt-5">
          <div><p className="ui-eyebrow">Administración</p><h1 className="ui-title">Usuarios</h1><p className="ui-description">Quién entra a Deck y con qué rol.</p></div>
          <Link to={`/users/new${search}`} className="inline-flex items-center gap-1.5 rounded-xl bg-accent px-3 py-2 text-sm font-medium text-accent-fg hover:opacity-90"><LuPlus className="h-4 w-4" />Crear usuario</Link>
        </div>
        <div className="admin-filters flex flex-wrap gap-2 px-5 py-3">
          <input type="search" aria-label="Buscar usuario" placeholder="Buscar usuario" value={q} onChange={(e) => setFilter("q", e.target.value)} className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-fg" />
          <select aria-label="Filtrar por estado" className={SELECT} value={estado} onChange={(e) => setFilter("estado", e.target.value)}>
            <option value="">Todos los estados</option>
            <option value="activo">Activos</option>
            <option value="desactivado">Desactivados</option>
          </select>
        </div>
        {status === "loading" && <p className="px-5 text-sm text-fg-subtle">Cargando…</p>}
        {status === "error" && <p role="alert" className="px-5 text-sm text-danger">{error}</p>}
        {status === "ready" && <UsersTable users={shown} selectedId={selected?.id} search={search} />}
        {onlyAdmin && <p className="px-5 py-4 text-sm text-fg-muted">Todavía no hay más usuarios. <Link to="/users/new" className="text-accent hover:underline">Crear usuario</Link></p>}
        {status === "ready" && shown.length === 0 && !onlyAdmin && <p className="px-5 py-4 text-sm text-fg-muted">Ningún usuario coincide con los filtros.</p>}
      </div>
      {id === "new" && <UserPanel key="new" closeTo={`/users${search}`} onCreate={createUser} onUpdate={updateUser} />}
      {id && id !== "new" && status === "ready" && (selected
        ? <UserPanel key={selected.id} user={selected} self={isSelf(selected)} closeTo={`/users${search}`} onCreate={createUser} onUpdate={updateUser}>
          <UserStatusSection user={selected} self={isSelf(selected)} onUpdate={updateUser} />
          <UserDelete user={selected} self={isSelf(selected)} onDeleted={() => afterDelete(() => navigate(`/users${search}`))} />
        </UserPanel>
        : <aside className="w-full shrink-0 border-l border-line p-5 md:w-96"><p className="text-sm text-fg-muted">Ese usuario no existe.</p><Link to={`/users${search}`} className="text-sm text-accent hover:underline">Volver a la tabla</Link></aside>)}
      </div>
    </div>
  );
}
