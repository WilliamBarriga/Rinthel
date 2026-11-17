import { LuLogOut } from "react-icons/lu";
import { navigationFor, type NavigationEntry } from "../navigation";
import { ThemeSwitcher } from "../components/ThemeSwitcher";

/**
 * The navigation column: the destinations of the registry the reader may visit, grouped, and who is
 * logged in with the way out.
 */
export function Sidebar({ navigation, current, isAdmin, username, onNavigate, onLogout }: {
  navigation: readonly NavigationEntry[];
  /** The id of the destination on screen. */
  current?: string;
  isAdmin: boolean;
  username?: string;
  onNavigate: (path: string) => void;
  onLogout: () => void;
}) {
  return (
    <nav aria-label="Navegación" className="sidebar-nav flex w-60 shrink-0 flex-col border-r border-line bg-canvas">
      <div className="flex items-center gap-2 px-4 py-4">
        <img src="/logo-192.png" alt="" className="h-7 w-7 object-contain" draggable={false} />
        <span className="text-sm font-semibold text-fg">Rinthel.Ai</span>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto px-2">
        {navigationFor(isAdmin ? "admin" : "usuario", navigation).map(({ group, entries }) => (
          <section key={group} aria-label={group}>
            {group === "administración" && <p className="px-2 pb-1 text-xs text-fg-subtle">Administración</p>}
            {entries.map(row => (
              <button key={row.id} type="button" onClick={() => onNavigate(row.path)} aria-current={row.id === current ? "page" : undefined}
                className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm ${row.id === current ? "bg-fg/5 text-fg" : "text-fg-muted hover:bg-fg/5 hover:text-fg"}`}>
                <span className="shrink-0"><row.icon className="h-4 w-4" /></span>{row.label}
              </button>
            ))}
          </section>
        ))}
      </div>
      <div className="space-y-2 border-t border-line p-3">
        <ThemeSwitcher />
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-xs text-fg-muted">{username}</span>
          <button type="button" onClick={onLogout} className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-fg-muted hover:bg-fg/5 hover:text-fg">
            <LuLogOut className="h-3.5 w-3.5" />Cerrar sesión
          </button>
        </div>
      </div>
    </nav>
  );
}
