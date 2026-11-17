import { useCallback, useEffect, useRef, useState } from "react";
import type { Canvas } from "@deck/contract";
import { useCanvasesApi } from "../ports/context";
import { messageOf } from "../ports/http-errors";
import { saveTextFile } from "./save-file";

/** A text file to hand to the person. */
export interface SavedFile {
  filename: string;
  text: string;
  mime: string;
}

export interface SessionCanvasesOptions {
  /** The panel is the Chat's: a Canvas the Agente creates, focuses or starts writing opens it. */
  setOpen: (open: boolean) => void;
  /** How a downloaded file reaches the person (the browser's download by default). */
  saveFile?: (file: SavedFile) => void;
}

/**
 * The file of a Canvas: its title as a file name (unsafe characters become `_`) and its content as
 * is. A `markdown` Canvas is a `.md`; a `ui` one holds a JSON spec, so it is a `.json`.
 */
export function canvasFile(canvas: Canvas): SavedFile {
  const name = canvas.title.replace(/[\\/:*?"<>|]/g, "_") || "canvas";
  return canvas.kind === "ui"
    ? { filename: `${name}.json`, text: canvas.content, mime: "application/json;charset=utf-8" }
    : { filename: `${name}.md`, text: canvas.content, mime: "text/markdown;charset=utf-8" };
}

const byNewest = (row: Canvas, rows: Canvas[]) => [row, ...rows.filter((c) => c.id !== row.id)];

/**
 * Controller of the Canvases of one Sesión, read only (the Agente writes them). It follows
 * `canvasesApi.stream`: every connection starts with a `snapshot`, and `create`, `update`, `focus`
 * and `delete` keep the list. It also reads `canvasesApi.list` when the Sesión changes, so the panel
 * has its Canvases before the stream answers; a read that was overtaken by a stream message is
 * dropped. A failed read becomes `error` until one works; nothing throws into a view.
 *
 * It follows the Agente: a `create`, a `focus` or a write that starts a new tool call (`active_call`
 * changes while the Canvas is `writing`) selects that Canvas and opens the panel, once per call, so
 * choosing another one afterwards sticks. `selected` is the chosen Canvas or the first. `download`
 * hands over the selected Canvas as a file (see `canvasFile`).
 */
export function useSessionCanvases(sessionId: string, { setOpen, saveFile = saveTextFile }: SessionCanvasesOptions) {
  const canvasesApi = useCanvasesApi();
  const [rows, setRows] = useState<Canvas[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const open = useRef(setOpen);
  open.current = setOpen;
  const updates = useRef(0);

  useEffect(() => {
    setRows([]);
    setSelectedId("");
    setError(null);
    open.current(false);
    updates.current = 0;
    let lastCall: string | null = null;
    const follow = (id: string) => {
      setSelectedId(id);
      open.current(true);
    };
    let disposed = false;
    const subscription = canvasesApi.stream(sessionId, (message) => {
      updates.current++;
      if (message.type === "snapshot") return setRows(message.canvases);
      if (message.type === "delete") return setRows((prev) => prev.filter((c) => c.id !== message.id));
      const { canvas } = message;
      setRows((prev) => byNewest(canvas, prev));
      if (message.type !== "update") follow(canvas.id);
      else if (canvas.status === "writing" && canvas.active_call !== lastCall) {
        lastCall = canvas.active_call;
        follow(canvas.id);
      }
    });
    const version = updates.current;
    canvasesApi.list(sessionId).then(
      (list) => {
        if (disposed || version !== updates.current) return;
        setRows(list);
        setError(null);
      },
      (e) => { if (!disposed) setError(messageOf(e)); },
    );
    return () => {
      disposed = true;
      subscription.close();
    };
  }, [sessionId, canvasesApi]);

  const selected = rows.find((c) => c.id === selectedId) ?? rows[0];
  const select = useCallback((id: string) => setSelectedId(id), []);
  const download = useCallback(() => {
    if (selected) saveFile(canvasFile(selected));
  }, [selected, saveFile]);

  return { canvases: rows, selected, select, error, download };
}
