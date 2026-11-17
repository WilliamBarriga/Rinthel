import { Link } from "react-router-dom";
import type { UserPublic } from "@deck/contract";

/** The users the filters let through, one row each; a disabled one is dimmed and marked. Opening a row is a link, so it is shareable. */
export function UsersTable({ users, selectedId, search }: {
  users: readonly UserPublic[];
  selectedId?: number;
  /** The current query string, kept on every link so opening a row does not drop the filters. */
  search: string;
}) {
  return (
    <div className="users-table-scroll" role="region" aria-label="Tabla de usuarios" tabIndex={0}><table className="users-table w-full text-left text-sm">
      <thead className="text-xs text-fg-subtle">
        <tr>
          {["Usuario", "Rol", "Estado"].map((h) => <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>)}
        </tr>
      </thead>
      <tbody>
        {users.map((u) => (
          <tr key={u.id} aria-selected={u.id === selectedId} className={`border-t border-line ${u.disabled ? "opacity-60" : ""} ${u.id === selectedId ? "bg-accent/5" : ""}`}>
            <td className="px-3 py-2"><Link to={`/users/${u.id}${search}`} className="text-fg hover:underline">{u.username}</Link></td>
            <td className="px-3 py-2">{u.role}</td>
            <td className="px-3 py-2">{u.disabled ? <span className="rounded bg-fg/5 px-1.5 py-0.5 text-xs text-fg-subtle">Desactivado</span> : "Activo"}</td>
          </tr>
        ))}
      </tbody>
    </table></div>
  );
}
