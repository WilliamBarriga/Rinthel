import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { LuMessageSquare, LuPlus, LuTrash2 } from "react-icons/lu";
import type { Session } from "@deck/contract";
import { useReportExpired } from "../failure-context";
import { useSessions } from "./use-sessions";

/** The landing screen: the reader's chats with the Agent and their task Sessions, and how to open a new one. */
export function SessionsPage({ username }: { username?: string }) {
  const navigate = useNavigate();
  const sessions = useSessions({ onFailure: useReportExpired(), onOpened: (id) => navigate(`/sessions/${id}`) });
  const [workspace, setWorkspace] = useState("");
  const [newWorkspace, setNewWorkspace] = useState("");
  const message = sessions.message;

  const addWorkspace = (e: FormEvent) => {
    e.preventDefault();
    const name = newWorkspace.trim();
    if (name) void sessions.createWorkspace(name).then((created) => { if (created) setNewWorkspace(""); });
  };

  return (
    <div className="space-y-6 px-5 py-5">
      <header>
        <p className="ui-eyebrow">Sesiones</p>
        <h1 className="ui-title">{username ? `Hola, ${username}` : "Hola"}</h1>
      </header>
      {sessions.error && <p role="alert" className="text-sm text-red-500">{sessions.error}</p>}
      {message && <p role="alert" className="text-sm text-red-500">{message}</p>}

      <section aria-label="Chats con el Agente" className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-fg">Chats con el Agente</h2>
          <button type="button" onClick={() => void sessions.createAgent()} className="flex items-center gap-1 rounded-lg border border-line px-2 py-1 text-xs text-fg hover:bg-fg/5">
            <LuPlus className="h-3.5 w-3.5" />Nuevo chat
          </button>
        </div>
        <SessionList rows={sessions.agent} onOpen={(id) => navigate(`/sessions/${id}`)} onRemove={(id) => void sessions.remove(id)} empty="Todavía no hay chats." />
      </section>

      <section aria-label="Tareas" className="space-y-2">
        <h2 className="text-sm font-semibold text-fg">Tareas</h2>
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="Workspace" value={workspace} onChange={(e) => setWorkspace(e.target.value)} className="rounded-lg border border-line bg-canvas px-2 py-1 text-xs text-fg">
            <option value="">Elige un workspace…</option>
            {sessions.workspaces.map((w) => <option key={w.name} value={w.name}>{w.name}</option>)}
          </select>
          <button type="button" disabled={!workspace} onClick={() => void sessions.createTask(workspace)} className="rounded-lg border border-line px-2 py-1 text-xs text-fg hover:bg-fg/5 disabled:opacity-40">
            Nueva tarea
          </button>
          <form onSubmit={addWorkspace} className="flex items-center gap-2">
            <input aria-label="Nuevo workspace" placeholder="Nuevo workspace" value={newWorkspace} onChange={(e) => setNewWorkspace(e.target.value)} className="rounded-lg border border-line bg-canvas px-2 py-1 text-xs" />
            <button type="submit" className="rounded-lg px-2 py-1 text-xs text-fg-muted hover:bg-fg/5">Crear</button>
          </form>
        </div>
        <SessionList rows={sessions.tasks} onOpen={(id) => navigate(`/sessions/${id}`)} onRemove={(id) => void sessions.remove(id)} empty="Todavía no hay tareas." />
      </section>
    </div>
  );
}

function SessionList({ rows, onOpen, onRemove, empty }: { rows: Session[]; onOpen: (id: string) => void; onRemove: (id: string) => void; empty: string }) {
  if (!rows.length) return <p className="text-xs text-fg-subtle">{empty}</p>;
  return (
    <ul className="divide-y divide-line rounded-xl border border-line">
      {rows.map((s) => (
        <li key={s.id} className="flex items-center gap-2 px-3 py-2">
          <button type="button" onClick={() => onOpen(s.id)} className="flex min-w-0 flex-1 items-center gap-2 text-left text-sm text-fg">
            <LuMessageSquare className="h-4 w-4 shrink-0 text-fg-subtle" />
            <span className="truncate">{s.title}</span>
            {s.status === "running" && <span className="text-xs text-fg-subtle">trabajando…</span>}
          </button>
          <button type="button" aria-label={`Borrar ${s.title}`} onClick={() => onRemove(s.id)} className="rounded-lg p-1 text-fg-subtle hover:bg-fg/5"><LuTrash2 className="h-3.5 w-3.5" /></button>
        </li>
      ))}
    </ul>
  );
}
