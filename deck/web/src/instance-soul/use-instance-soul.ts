import { useCallback, useEffect, useRef, useState } from "react";
import type { InstanceSoul } from "@deck/contract";
import { useInstanceSoulApi } from "../ports/context";
import { messageOf } from "../ports/http-errors";
import { useRemote } from "../use-remote";

/**
 * Controller of the Instance SOUL screen, through `instanceSoulApi`. `content` is what is in the
 * editor (`setContent` edits it); `editable` says whether the reader is an admin, who may `save`
 * (a member sees the same text read-only). A refused save leaves `actionError` and the editor as typed;
 * `saved` is the brief "Guardada" flash.
 */
export function useInstanceSoul({ onFailure }: { onFailure?: (error: unknown) => void } = {}) {
  const api = useInstanceSoulApi();
  const [content, setContent] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const flash = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(flash.current), []);

  // The editor takes the answer in the same tick the read ends, so it never shows a stale buffer.
  const read = useCallback(async (): Promise<InstanceSoul> => {
    const soul = await api.read();
    setContent(soul.content);
    return soul;
  }, [api]);
  const remote = useRemote(read, { onFailure });

  const save = useCallback(async (): Promise<boolean> => {
    setBusy(true);
    setActionError(null);
    try {
      const soul = await api.save(content);
      setContent(soul.content);
      setSaved(true);
      clearTimeout(flash.current);
      flash.current = setTimeout(() => setSaved(false), 2000);
      return true;
    } catch (e) {
      onFailure?.(e);
      setActionError(messageOf(e));
      return false;
    } finally {
      setBusy(false);
    }
  }, [api, content, onFailure]);

  return {
    status: remote.status,
    error: remote.status === "error" ? messageOf(remote.error) : null,
    soul: remote.data,
    editable: remote.data?.editable ?? false,
    content, setContent, save, busy, saved, actionError,
  };
}
