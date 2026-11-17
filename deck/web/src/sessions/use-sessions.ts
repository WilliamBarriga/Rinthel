import { useCallback, useState } from "react";
import type { Session } from "@deck/contract";
import { useSessionsApi } from "../ports/context";
import { useRemote } from "../use-remote";
import { messageOf } from "../ports/http-errors";

/**
 * Controller of Sesiones: the reader's chats with the Agent, their `task` Sessions and the workspaces
 * they may open one on. A new Session is handed to `onOpened` (to open it); a refusal stays as `message`.
 */
export function useSessions({ onFailure, onOpened }: { onFailure?: (error: unknown) => void; onOpened?: (id: string) => void } = {}) {
  const api = useSessionsApi();
  const read = useCallback(async () => {
    const [agent, tasks, spaces] = await Promise.all([api.listAgent(), api.listTask(), api.listWorkspaces()]);
    return { agent: agent.sessions, tasks, workspaces: spaces.workspaces };
  }, [api]);
  const remote = useRemote(read, { onFailure });

  const [message, setMessage] = useState<string | null>(null);
  const create = useCallback(async (make: () => Promise<Session>): Promise<void> => {
    setMessage(null);
    try {
      const session = await make();
      await remote.reload();
      onOpened?.(session.id);
    } catch (e) {
      onFailure?.(e);
      setMessage(messageOf(e));
    }
  }, [remote.reload, onFailure, onOpened]);

  const createAgent = useCallback(() => create(() => api.createAgent()), [api, create]);
  const createTask = useCallback((workspace: string) => create(() => api.createTask(workspace)), [api, create]);
  /** Answers whether it was created, so the form can clear its field. */
  const createWorkspace = useCallback(async (name: string): Promise<boolean> => {
    setMessage(null);
    try {
      await api.createWorkspace(name);
      await remote.reload();
      return true;
    } catch (e) {
      setMessage(messageOf(e));
      return false;
    }
  }, [api, remote.reload]);
  const remove = useCallback(async (id: string) => {
    try { await api.remove(id); } catch (e) { onFailure?.(e); }
    await remote.reload();
  }, [api, remote.reload, onFailure]);

  return {
    status: remote.status,
    error: remote.status === "error" ? messageOf(remote.error) : null,
    message,
    agent: remote.data?.agent ?? [],
    tasks: remote.data?.tasks ?? [],
    workspaces: remote.data?.workspaces ?? [],
    createAgent, createTask, createWorkspace, remove,
  };
}
